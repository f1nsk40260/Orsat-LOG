"""Synchronisation du carnet de trafic avec le logbook QRZ.com (QRZ Logbook API).

Documentation : https://www.qrz.com/docs/logbook/QRZLogbookAPI.html
  - POST https://logbook.qrz.com/api, champs KEY + ACTION (FETCH, INSERT, DELETE, STATUS).
  - Réponse « CLÉ=valeur&CLÉ=valeur », l'ADIF y est encodé en entités HTML (&lt; &gt;).
  - Chaque QSO a chez QRZ un numéro unique : app_qrzlog_logid.
  - User-Agent obligatoire et spécifique (« Application/version »).

Règles (décisions F1NSK, 21/10/2026) :
  - QRZ -> carnet : tout le logbook au premier passage, puis les modifications (MODSINCE).
  - Carnet -> QRZ : chaque contact saisi ou corrigé dans le carnet (état « pending »).
  - Les écoutes SWL ne partent JAMAIS (db.qrz_pending ne renvoie que kind = 'QSO').
  - Suppressions : jamais automatiques ; le carnet demande à l'opérateur à chaque suppression
    d'un contact synchronisé s'il faut aussi le supprimer chez QRZ (suppression définitive).
"""

import asyncio
import html
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from datetime import datetime, timedelta, timezone

from . import __version__, adif, enrich, geo

log = logging.getLogger("orsatlog.qrz")

API_URL = os.environ.get("ORSATLOG_QRZ_URL", "https://logbook.qrz.com/api")   # variable : essais
USER_AGENT = f"ORSAT-LOG/{__version__} (F1NSK)"
PAGE = 250                 # enregistrements par lecture (valeur conseillée par QRZ)
PERIOD = 15 * 60           # synchronisation automatique toutes les 15 min
PAUSE = 0.4                # entre deux requêtes, pour ménager QRZ

# Champs que le carnet gère lui-même (le reste de l'enregistrement QRZ va dans adif_extra)
_OWN = {"CALL", "QSO_DATE", "TIME_ON", "BAND", "FREQ", "MODE", "SUBMODE", "RST_SENT", "RST_RCVD",
        "NAME", "QTH", "GRIDSQUARE", "COMMENT", "NOTES"}
# Champs tenus par QRZ, jamais renvoyés
_QRZ_ONLY = re.compile(r"^(APP_QRZLOG_|QRZCOM_QSO_)")
_KEYS = ("RESULT", "REASON", "COUNT", "LOGIDS", "LOGID", "DATA", "EXTENDED", "ADIF")


class QrzError(Exception):
    pass


def parse_response(text):
    """Découpe « RESULT=OK&COUNT=2&ADIF=<...> » sans casser sur les & contenus dans l'ADIF :
    seules les clés connues de l'API servent de séparateurs."""
    out = {}
    marks = [(m.start(), m.end(), m.group(2))
             for m in re.finditer(r"(^|&)(%s)=" % "|".join(_KEYS), text)]
    for i, (_, end, key) in enumerate(marks):
        stop = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        value = text[end:stop]
        out[key] = html.unescape(value) if key == "ADIF" else urllib.parse.unquote_plus(value)
    return out


class QrzClient:
    def __init__(self, key, timeout=60):
        self.key = key.strip()
        self.timeout = timeout

    def call(self, action, **params):
        data = urllib.parse.urlencode({"KEY": self.key, "ACTION": action, **params}).encode()
        req = urllib.request.Request(API_URL, data=data, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                text = r.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as exc:
            raise QrzError(f"QRZ.com injoignable : {getattr(exc, 'reason', exc)}")
        res = parse_response(text)
        result = res.get("RESULT", "")
        if result == "AUTH":
            raise QrzError("clé refusée ou abonnement insuffisant (RESULT=AUTH)")
        if result == "FAIL":
            reason = res.get("REASON", "")
            # FETCH sans résultat (« rien de nouveau ») : QRZ répond FAIL ; ce n'est pas une erreur
            empty = res.get("COUNT") == "0" or re.search(r"no (log )?(entries|records|qsos?)|not found", reason, re.I)
            if not (action == "FETCH" and empty):
                raise QrzError(reason or "échec sans motif")
        return res

    def status(self):
        return self.call("STATUS").get("DATA", "")

    def fetch(self, option):
        """Enregistrements ADIF -> liste de dict {CHAMP: valeur}."""
        res = self.call("FETCH", OPTION=option)
        text = res.get("ADIF", "")
        return adif.parse(("<EOH>" + text).encode()) if text else []

    def insert(self, adif_text, replace=False):
        params = {"ADIF": adif_text}
        if replace:
            params["OPTION"] = "REPLACE"
        res = self.call("INSERT", **params)
        logid = res.get("LOGID") or (res.get("LOGIDS") or "").split(",")[0]
        return res.get("RESULT", ""), int(logid) if str(logid).isdigit() else None

    def delete(self, logid):
        self.call("DELETE", LOGIDS=str(logid))


# ---------- conversions ----------
def _key_of(q):
    return (q["call"].upper(), q["qso_date"], (q["time_on"] or "")[:4], (q.get("band") or "").lower())


def record_to_fields(rec, settings):
    """Enregistrement QRZ -> (champs du carnet, adif_extra) ; None si pas un contact."""
    q, _why = adif.to_entry(rec)
    if q is None:
        return None, None
    q["band"] = geo.band_of(q["freq"]) or q["band"]
    extra = {k: v for k, v in rec.items() if k not in _OWN and not _QRZ_ONLY.match(k)}
    p = enrich.promote(extra)                   # QTH d'émission, pays, DXCC, confirmation…
    q.update({k: v for k, v in p.items() if v is not None})
    q["country"] = p["country"] or ""
    q["distance_km"], q["bearing"] = enrich.geometry(q, settings)
    return q, extra


def fields_to_adif(q, settings):
    """QSO du carnet -> enregistrement ADIF pour QRZ (champs QRZ conservés + champs du carnet)."""
    rec = {}
    try:
        rec.update(json.loads(q.get("adif_extra") or "{}"))
    except ValueError:
        pass
    rec = {k: v for k, v in rec.items() if not _QRZ_ONLY.match(k)}
    own = {
        "CALL": q["call"], "QSO_DATE": q["qso_date"], "TIME_ON": q["time_on"],
        "BAND": q.get("band") or "", "MODE": q.get("mode") or "", "SUBMODE": q.get("submode") or "",
        "FREQ": f"{q['freq'] / 1e6:.6f}" if q.get("freq") else "",
        "RST_SENT": q.get("rst_sent") or "", "RST_RCVD": q.get("rst_rcvd") or "",
        "NAME": q.get("name") or "", "QTH": q.get("qth") or "",
        "GRIDSQUARE": q.get("gridsquare") or "", "COMMENT": q.get("comment") or "",
    }
    rec.update({k: v for k, v in own.items() if v != ""})
    if settings.get("callsign"):
        rec.setdefault("STATION_CALLSIGN", settings["callsign"])
    if q.get("my_gridsquare") or settings.get("locator"):
        rec.setdefault("MY_GRIDSQUARE", q.get("my_gridsquare") or settings["locator"])
    return "".join(f"<{k.lower()}:{len(str(v))}>{v}" for k, v in rec.items()) + "<eor>"


# ---------- moteur ----------
class QrzSync:
    def __init__(self, db):
        self.db = db
        self.journal = deque(maxlen=200)
        self.state = {"running": False, "last_run": "", "last_ok": "", "last_error": "",
                      "pulled": 0, "pushed": 0}
        self._wake = asyncio.Event()
        self._lock = asyncio.Lock()

    def note(self, msg, level=logging.INFO):
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self.journal.append(f"{stamp}  {msg}")
        log.log(level, "QRZ : %s", msg)

    def settings(self):
        return self.db.get_settings()

    def enabled(self):
        s = self.settings()
        return s.get("qrz_sync") == "1" and bool(s.get("qrz_api_key", "").strip())

    def poke(self):
        """Un contact vient d'être saisi ou corrigé : envoi dans les secondes qui suivent."""
        self._wake.set()

    async def loop(self):
        await asyncio.sleep(20)                     # laisser démarrer le carnet
        while True:
            if self.enabled():
                await self.run()
            try:
                await asyncio.wait_for(self._wake.wait(), PERIOD)
                await asyncio.sleep(5)              # regrouper une rafale de saisies
            except asyncio.TimeoutError:
                pass
            self._wake.clear()

    async def run(self, full=False):
        if self._lock.locked():
            return False
        async with self._lock:
            self.state.update(running=True, last_run=_now())
            try:
                await asyncio.to_thread(self._run, full)
                self.state.update(last_ok=_now(), last_error="")
                return True
            except QrzError as exc:
                self.state["last_error"] = str(exc)
                self.note(f"ERREUR : {exc}", logging.WARNING)
            except Exception as exc:                    # ne jamais faire tomber le carnet
                self.state["last_error"] = str(exc)
                self.note(f"ERREUR inattendue : {exc}", logging.ERROR)
            finally:
                self.state["running"] = False
            return False

    # -- une passe complète : lire QRZ, puis envoyer les contacts du carnet --
    def _run(self, full):
        s = self.settings()
        client = QrzClient(s.get("qrz_api_key", ""))
        if full or s.get("qrz_full_done") != "1":
            self._pull_all(client, s)
            self.db.set_settings({"qrz_full_done": "1"})
            self.db.qrz_mark_all_pending()          # contacts du carnet absents de QRZ
        else:
            since = s.get("qrz_last_pull") or "2000-01-01"
            self._pull_since(client, s, since)
        self.db.set_settings({"qrz_last_pull": (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")})
        self._push(client, s)
        enrich.run(self.db)                     # SFI / A / K historiques des nouveaux contacts

    def _pull_all(self, client, s):
        self.note("Lecture complète du logbook QRZ…")
        after, total = 0, 0
        while True:
            recs = client.fetch(f"MAX:{PAGE},AFTERLOGID:{after}")
            if not recs:
                break
            total += self._merge(recs, s)
            ids = [int(r["APP_QRZLOG_LOGID"]) for r in recs if r.get("APP_QRZLOG_LOGID", "").isdigit()]
            if not ids or len(recs) < PAGE:
                break
            after = max(ids) + 1
            time.sleep(PAUSE)
        self.note(f"Logbook QRZ lu : {total} contact(s) ajouté(s) ou mis à jour dans le carnet.")

    def _pull_since(self, client, s, since):
        recs = client.fetch(f"MODSINCE:{since}")
        n = self._merge(recs, s) if recs else 0
        if n:
            self.note(f"{n} contact(s) modifié(s) chez QRZ depuis le {since} repris dans le carnet.")

    def _merge(self, recs, s):
        changed = 0
        ignored = self.db.qrz_ignored()          # retirés du carnet à la demande de l'opérateur
        for rec in recs:
            logid = int(rec["APP_QRZLOG_LOGID"]) if rec.get("APP_QRZLOG_LOGID", "").isdigit() else None
            q, extra = record_to_fields(rec, s)
            if q is None or logid is None or logid in ignored:
                continue
            local = self.db.qrz_find(logid=logid, key=_key_of(q))
            fields = {**q, "qrz_logid": logid, "qrz_state": "synced", "qrz_error": None,
                      "adif_extra": json.dumps(extra, ensure_ascii=False)}
            if local is None:
                fields["kind"] = "QSO"
                self.db.add_qso(fields)
                changed += 1
            elif local.get("qrz_state") == "pending" and local.get("qrz_logid") == logid:
                # corrigé dans le carnet, pas encore envoyé : la version du carnet l'emporte,
                # on garde seulement les champs QRZ à jour (confirmations…)
                self.db.update_qso(local["id"], {"adif_extra": fields["adif_extra"]})
            else:
                fields.pop("kind", None)
                self.db.update_qso(local["id"], fields)
                changed += 1
        self.state["pulled"] += changed
        return changed

    def _push(self, client, s):
        sent = 0
        while True:
            batch = self.db.qrz_pending()
            if not batch:
                break
            progress = False
            for q in batch:
                try:
                    self._push_one(client, s, q)
                    sent += 1
                    progress = True
                except QrzError as exc:
                    self.db.update_qso(q["id"], {"qrz_state": "error", "qrz_error": str(exc)[:300]})
                    self.note(f"{q['call']} {q['qso_date']} : refusé par QRZ ({exc})", logging.WARNING)
                    if "AUTH" in str(exc) or "injoignable" in str(exc):
                        raise
                time.sleep(PAUSE)
            if not progress:
                break
        if sent:
            self.note(f"{sent} contact(s) envoyé(s) vers QRZ.")
        self.state["pushed"] += sent

    def _push_one(self, client, s, q):
        old = q.get("qrz_logid")
        if old:
            # Corrigé dans le carnet : on relit d'abord l'enregistrement QRZ (confirmations
            # reçues entre-temps), puis on le remplace.
            recs = client.fetch(f"LOGIDS:{old}")
            if recs:
                _, extra = record_to_fields(recs[0], s)
                q["adif_extra"] = json.dumps(extra or {}, ensure_ascii=False)
        result, logid = client.insert(fields_to_adif(q, s), replace=bool(old))
        if not logid:
            raise QrzError(f"réponse sans numéro de QSO (RESULT={result})")
        if old and logid != old:
            # Indicatif, date ou heure changés : QRZ a créé un nouvel enregistrement.
            client.delete(old)
            self.note(f"{q['call']} : ancien enregistrement QRZ {old} remplacé par {logid}.")
        self.db.update_qso(q["id"], {"qrz_logid": logid, "qrz_state": "synced", "qrz_error": None,
                                     "adif_extra": q.get("adif_extra")})

    # -- suppression demandée par l'opérateur --
    def delete_remote(self, logid):
        client = QrzClient(self.settings().get("qrz_api_key", ""))
        client.delete(logid)
        self.note(f"QSO {logid} supprimé du logbook QRZ (à la demande de l'opérateur).")

    def test_key(self, key):
        data = QrzClient(key).status()
        return data


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
