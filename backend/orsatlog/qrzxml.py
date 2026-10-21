"""Annuaire QRZ.com (service XML) : photo, prénom, nom et QTH d'un indicatif.

Ce n'est pas la clé du logbook : l'annuaire se consulte avec l'identifiant et le mot de passe du
compte QRZ (https://www.qrz.com/docs/xml/current_spec.html) :
  1. https://xmldata.qrz.com/xml/current/?username=…;password=…;agent=…  -> <Session><Key>
  2. https://xmldata.qrz.com/xml/current/?s=<clé>;callsign=…              -> <Callsign> fname, name,
     addr2 (ville), country, image (URL de la photo)…
Sans abonnement XML, QRZ ne renvoie qu'une partie des champs (la photo peut manquer) : le
message <Session><Message> est alors transmis tel quel. Réponses gardées 30 jours.
"""

import json
import logging
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from . import __version__

log = logging.getLogger("orsatlog.qrzxml")

URL = "https://xmldata.qrz.com/xml/current/"
AGENT = f"ORSAT-LOG-{__version__}"
CACHE_S = 30 * 86400


class QrzXmlError(Exception):
    pass


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _parse(text):
    root = ET.fromstring(text)
    out = {"session": {}, "callsign": {}}
    for part in root:
        name = _local(part.tag).lower()
        if name in out:
            for f in part:
                out[name][_local(f.tag).lower()] = (f.text or "").strip()
    return out


class QrzXml:
    def __init__(self, db):
        self.db = db
        self.key = None
        self._lock = threading.Lock()
        with db._lock:
            db._con.execute("CREATE TABLE IF NOT EXISTS qrz_lookup (call TEXT PRIMARY KEY, data TEXT, at REAL)")
            db._con.commit()

    def _creds(self):
        s = self.db.get_settings()
        return s.get("qrz_xml_user", ""), s.get("qrz_xml_password", "")

    def _get(self, params):
        url = URL + "?" + ";".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
        req = urllib.request.Request(url, headers={"User-Agent": AGENT})
        with urllib.request.urlopen(req, timeout=15) as r:
            return _parse(r.read().decode("utf-8", errors="replace"))

    def login(self, user=None, password=None):
        u, p = (user, password) if user is not None else self._creds()
        if not u or not p:
            raise QrzXmlError("identifiant et mot de passe QRZ non réglés (panneau admin → Carnet ORSAT-LOG)")
        d = self._get({"username": u, "password": p, "agent": AGENT})
        key = d["session"].get("key")
        if not key:
            raise QrzXmlError(d["session"].get("error") or "connexion refusée par QRZ.com")
        if user is None:
            self.key = key
        return d["session"]

    def forget(self):
        self.key = None
        with self.db._lock:
            self.db._con.execute("DELETE FROM qrz_lookup")
            self.db._con.commit()

    def lookup(self, call):
        call = (call or "").strip().upper()
        if not call:
            raise QrzXmlError("indicatif vide")
        with self.db._lock:
            r = self.db._con.execute("SELECT data, at FROM qrz_lookup WHERE call = ?", (call,)).fetchone()
        if r and time.time() - r["at"] < CACHE_S:
            cached = json.loads(r["data"])
            if "grid" in cached:            # réponses d'avant v1.11.5 : sans locator, on redemande
                return cached
        with self._lock:
            for attempt in (1, 2):
                if not self.key:
                    self.login()
                d = self._get({"s": self.key, "callsign": call})
                err = d["session"].get("error", "")
                if not d["session"].get("key") or "session" in err.lower() and "invalid" in err.lower() \
                        or "timeout" in err.lower():
                    self.key = None              # session expirée : on se reconnecte une fois
                    if attempt == 1:
                        continue
                break
        c = d["callsign"]
        if not c:
            raise QrzXmlError(err or "indicatif inconnu de QRZ.com")
        out = {"call": c.get("call", call), "fname": c.get("fname", ""), "name": c.get("name", ""),
               "nickname": c.get("nickname", ""), "qth": c.get("addr2", ""), "state": c.get("state", ""),
               "country": c.get("country", ""), "image": c.get("image", ""),
               "grid": c.get("grid", "").upper(),
               "notice": d["session"].get("message", "")}
        with self.db._lock:
            self.db._con.execute("INSERT OR REPLACE INTO qrz_lookup (call, data, at) VALUES (?, ?, ?)",
                                 (call, json.dumps(out), time.time()))
            self.db._con.commit()
        return out
