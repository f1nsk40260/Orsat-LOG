"""Synchronisation du carnet de trafic avec eQSL.cc.

API eQSL (https://www.eqsl.cc/qslcard/ADIFContentSpecs.cfm, ImportADIF.cfm, DownloadInBox.cfm) :
  - Envoi : POST https://www.eqsl.cc/qslcard/ImportADIF.cfm, champ ADIFData = un fichier ADIF dont
    l'en-tête porte EQSL_USER et EQSL_PSWD. Réponse HTML : « Result: 1 out of 1 records added »,
    « Warning: … Duplicate » (déjà chez eQSL) ou « Error: … ».
  - Confirmations reçues : GET DownloadInBox.cfm?UserName=…&Password=…&RcvdSince=AAAAMMJJHHMM ;
    la page donne un lien vers un fichier .adi (les eQSL reçues), ou « You have no log entries ».

Règles (demande F1NSK, 02/11/2026) :
  - Seuls les contacts du carnet de trafic partent (kind = 'QSO'), JAMAIS les écoutes SWL.
  - Un QSO part une fois. eQSL ne sait ni corriger ni supprimer par l'API : un QSO déjà envoyé
    puis corrigé (indicatif, date, heure, bande, mode) repart, l'ancienne version est à
    supprimer à la main sur eQSL (noté au journal).
  - Seuls les QSO à partir de la date choisie dans le panneau admin partent (par défaut le jour
    de la mise en service) : l'historique n'est pas envoyé d'un coup sans le vouloir.
  - Les confirmations eQSL reçues marquent le QSO « confirmé eQSL » (colonne eqsl_rcvd).
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

from . import __version__, adif
from .geo import ADIF_BANDS

log = logging.getLogger("orsatlog.eqsl")

BASE_URL = os.environ.get("ORSATLOG_EQSL_URL", "https://www.eqsl.cc/qslcard/")   # variable : essais
USER_AGENT = f"ORSAT-LOG/{__version__} (F1NSK)"
PERIOD = 15 * 60           # envoi automatique toutes les 15 min (et ~5 s après une saisie)
INBOX_PERIOD = 3 * 3600    # relève des eQSL reçues toutes les 3 h
PAUSE = 1.0                # entre deux envois, pour ménager eQSL
MATCH_MINUTES = 30         # écart d'heure toléré pour rapprocher une eQSL reçue (règle eQSL)


class EqslError(Exception):
    pass


class EqslAuthError(EqslError):
    pass


def _text(page):
    """Page HTML eQSL -> texte brut, une ligne par <br>/paragraphe."""
    page = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>", "\n", page)
    page = re.sub(r"<[^>]+>", " ", page)
    lines = (re.sub(r"[ \t]+", " ", html.unescape(x)).strip() for x in page.splitlines())
    return "\n".join(x for x in lines if x)


_AUTH = re.compile(r"no match on eqsl_user|no such username|password.*(incorrect|invalid)|"
                   r"invalid (user|password|login)|not authorized|(user|login).*not found", re.I)


class EqslClient:
    def __init__(self, user, password, nickname="", timeout=60):
        self.user = user.strip().upper()
        self.password = password
        self.nickname = (nickname or "").strip()
        self.timeout = timeout

    def _open(self, url, data=None):
        req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
        except urllib.error.HTTPError as exc:
            raise EqslError(f"eQSL.cc a répondu {exc.code}")
        except urllib.error.URLError as exc:
            raise EqslError(f"eQSL.cc injoignable : {getattr(exc, 'reason', exc)}")
        except TimeoutError:
            raise EqslError("eQSL.cc injoignable : délai dépassé")
        return raw

    # -- envoi d'un QSO --
    def upload(self, record):
        """Envoie UN enregistrement ADIF. Renvoie 'added' ou 'duplicate' ; EqslError sinon."""
        head = ("ORSAT-LOG upload\n" + _f("ADIF_VER", "3.1.4") + _f("PROGRAMID", "ORSAT-LOG")
                + _f("EQSL_USER", self.user) + _f("EQSL_PSWD", self.password) + "<EOH>\n")
        data = urllib.parse.urlencode({"ADIFData": head + record}).encode()
        text = _text(self._open(urllib.parse.urljoin(BASE_URL, "ImportADIF.cfm"), data)
                     .decode("utf-8", errors="replace"))
        return parse_upload(text)

    # -- eQSL reçues --
    def inbox(self, since=""):
        """eQSL reçues depuis since (AAAAMMJJHHMM, vide = toutes) -> enregistrements ADIF."""
        q = {"UserName": self.user, "Password": self.password}
        if since:
            q["RcvdSince"] = since
        if self.nickname:
            q["QTHNickname"] = self.nickname
        url = urllib.parse.urljoin(BASE_URL, "DownloadInBox.cfm?" + urllib.parse.urlencode(q))
        page = self._open(url).decode("utf-8", errors="replace")
        m = re.search(r'href\s*=\s*"?([^"\s>]+\.adi)', page, re.I)
        if not m:
            text = _text(page)
            if re.search(r"no (log )?entries|no records|nothing", text, re.I):
                return []
            err = re.search(r"error:?\s*(.+)", text, re.I)
            msg = err.group(1).strip() if err else (text[:200] or "réponse vide")
            if _AUTH.search(text):
                raise EqslAuthError(f"identifiants refusés ({msg})")
            raise EqslError(msg)
        raw = self._open(urllib.parse.urljoin(url, m.group(1)))
        return adif.parse(raw)

    def check(self):
        """Vérifie identifiant / mot de passe (relève vide depuis maintenant)."""
        self.inbox(datetime.now(timezone.utc).strftime("%Y%m%d%H%M"))


def parse_upload(text):
    """Réponse d'ImportADIF -> 'added' / 'duplicate', ou EqslError avec le motif d'eQSL."""
    if _AUTH.search(text):
        raise EqslAuthError("identifiants refusés par eQSL.cc")
    m = re.search(r"Result:\s*(\d+)\s+out of\s+(\d+)\s+records?\s+added", text, re.I)
    if m and int(m.group(1)) >= 1:
        return "added"
    if re.search(r"duplicate", text, re.I):
        return "duplicate"
    err = re.search(r"(?:Error|Warning|Caution):?\s*(.+)", text, re.I)
    raise EqslError(err.group(1).strip()[:300] if err else (text.strip()[:300] or "réponse vide"))


def _f(tag, value):
    value = str(value)
    return f"<{tag}:{len(value)}>{value}"


def record_of(q, settings, nickname=""):
    """QSO du carnet -> enregistrement ADIF pour eQSL (le strict nécessaire à une eQSL)."""
    rec = {
        "CALL": q["call"], "QSO_DATE": q["qso_date"], "TIME_ON": (q.get("time_on") or "")[:4],
        "BAND": q.get("band") if q.get("band") in ADIF_BANDS else "",
        "MODE": q.get("mode") or "", "SUBMODE": q.get("submode") or "",
        "FREQ": f"{q['freq'] / 1e6:.6f}" if q.get("freq") else "",
        "RST_SENT": q.get("rst_sent") or "",
        "MY_GRIDSQUARE": q.get("my_gridsquare") or settings.get("locator") or "",
        "APP_EQSL_QTH_NICKNAME": nickname,
    }
    return "".join(_f(k, v) for k, v in rec.items() if v) + "<EOR>\n"


def eqsl_key(q):
    """Ce qui fait l'identité d'un QSO chez eQSL : s'il change, le QSO doit repartir."""
    return (q.get("call", "").upper(), q.get("qso_date"), (q.get("time_on") or "")[:4],
            (q.get("band") or "").lower(), (q.get("mode") or "").upper())


def _already_sent(q):
    try:
        extra = json.loads(q.get("adif_extra") or "{}")
    except ValueError:
        return False
    return str(extra.get("EQSL_QSL_SENT", "")).upper() == "Y"


def _minutes(hhmm):
    try:
        return int(hhmm[:2]) * 60 + int(hhmm[2:4])
    except (TypeError, ValueError):
        return None


# ---------- moteur ----------
class EqslSync:
    def __init__(self, db):
        self.db = db
        self.journal = deque(maxlen=200)
        self.state = {"running": False, "last_run": "", "last_ok": "", "last_error": "",
                      "sent": 0, "confirmed": 0, "last_inbox": ""}
        self._wake = asyncio.Event()
        self._lock = asyncio.Lock()
        self._inbox_at = 0.0

    def note(self, msg, level=logging.INFO):
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self.journal.append(f"{stamp}  {msg}")
        log.log(level, "eQSL : %s", msg)

    def enabled(self):
        s = self.db.get_settings()
        return s.get("eqsl_sync") == "1" and bool(s.get("eqsl_user")) and bool(s.get("eqsl_password"))

    def poke(self):
        """Un contact vient d'être saisi ou corrigé : envoi dans les secondes qui suivent."""
        self._wake.set()

    def client(self, s=None):
        s = s or self.db.get_settings()
        return EqslClient(s.get("eqsl_user", ""), s.get("eqsl_password", ""), s.get("eqsl_nickname", ""))

    async def loop(self):
        await asyncio.sleep(40)                     # laisser démarrer le carnet (et la synchro QRZ)
        while True:
            if self.enabled():
                await self.run()
            try:
                await asyncio.wait_for(self._wake.wait(), PERIOD)
                await asyncio.sleep(5)              # regrouper une rafale de saisies
            except asyncio.TimeoutError:
                pass
            self._wake.clear()

    async def run(self, inbox=False, retry=False):
        if self._lock.locked():
            return False
        async with self._lock:
            self.state.update(running=True, last_run=_now())
            try:
                await asyncio.to_thread(self._run, inbox, retry)
                self.state.update(last_ok=_now(), last_error="")
                return True
            except EqslError as exc:
                self.state["last_error"] = str(exc)
                self.note(f"ERREUR : {exc}", logging.WARNING)
            except Exception as exc:                    # ne jamais faire tomber le carnet
                self.state["last_error"] = str(exc)
                self.note(f"ERREUR inattendue : {exc}", logging.ERROR)
            finally:
                self.state["running"] = False
            return False

    def _run(self, inbox, retry):
        s = self.db.get_settings()
        client = self.client(s)
        if retry:
            n = self.db.eqsl_retry_errors()
            if n:
                self.note(f"{n} QSO refusé(s) remis en attente.")
        self._push(client, s)
        if inbox or time.time() - self._inbox_at > INBOX_PERIOD:
            self._pull_inbox(client, s)

    def _push(self, client, s):
        since = s.get("eqsl_since", "")
        nick = s.get("eqsl_nickname", "")
        sent = dup = 0
        while True:
            batch = self.db.eqsl_pending(since)
            if not batch:
                break
            for q in batch:
                if q["kind"] != "QSO":              # garde-fou : jamais une écoute
                    continue
                if _already_sent(q):                # déjà envoyé à eQSL (noté chez QRZ.com)
                    self.db.update_qso(q["id"], {"eqsl_state": "synced", "eqsl_error": None})
                    dup += 1
                    continue
                try:
                    res = client.upload(record_of(q, s, nick))
                except EqslAuthError:
                    raise
                except EqslError as exc:
                    if "injoignable" in str(exc):
                        raise
                    self.db.update_qso(q["id"], {"eqsl_state": "error", "eqsl_error": str(exc)[:300]})
                    self.note(f"{q['call']} {q['qso_date']} : refusé par eQSL ({exc})", logging.WARNING)
                    time.sleep(PAUSE)
                    continue
                self.db.update_qso(q["id"], {"eqsl_state": "synced", "eqsl_error": None})
                if res == "duplicate":
                    dup += 1
                else:
                    sent += 1
                time.sleep(PAUSE)
        if sent or dup:
            self.note(f"{sent} QSO envoyé(s) vers eQSL" + (f", {dup} y étai(en)t déjà." if dup else "."))
        self.state["sent"] += sent

    def _pull_inbox(self, client, s):
        since = s.get("eqsl_last_inbox", "")
        started = datetime.now(timezone.utc)
        recs = client.inbox(since)
        n = 0
        for rec in recs:
            n += self._confirm(rec)
        # la prochaine relève reprend un jour avant, au cas où une eQSL arriverait en retard
        self.db.set_settings({"eqsl_last_inbox": (started - timedelta(days=1)).strftime("%Y%m%d%H%M")})
        self._inbox_at = time.time()
        self.state["last_inbox"] = _now()
        self.state["confirmed"] += n
        if n:
            self.note(f"{n} QSO confirmé(s) par eQSL ({len(recs)} eQSL relue(s)).")
        elif not since:
            self.note(f"Boîte eQSL relue en entier : {len(recs)} eQSL, aucun QSO du carnet à confirmer.")

    def _confirm(self, rec):
        """Une eQSL reçue -> QSO du carnet de trafic confirmé (même indicatif, date, bande, ±30 min)."""
        call = (rec.get("CALL") or "").strip().upper()
        date = re.sub(r"\D", "", rec.get("QSO_DATE", ""))
        t = _minutes(re.sub(r"\D", "", rec.get("TIME_ON", "")))
        band = (rec.get("BAND") or "").lower()
        if not call or len(date) != 8 or t is None:
            return 0
        best = None
        for q in self.db.eqsl_candidates(call, date):
            if q.get("eqsl_rcvd"):
                continue
            if band and q.get("band") and q["band"].lower() != band:
                continue
            m = _minutes(q.get("time_on"))
            if m is None or abs(m - t) > MATCH_MINUTES:
                continue
            if best is None or abs(m - t) < abs(_minutes(best["time_on"]) - t):
                best = q
        if not best:
            return 0
        rdate = re.sub(r"\D", "", rec.get("QSLRDATE", "")) or datetime.now(timezone.utc).strftime("%Y%m%d")
        change = {"eqsl_rcvd": rdate[:8]}
        if not best.get("confirmed"):
            change["confirmed"] = "eQSL"
        self.db.update_qso(best["id"], change)
        return 1


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
