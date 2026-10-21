"""Identification des écoutes SWL par la grille EiBi (http://www.eibispace.de/dx/).

EiBi (Eike Bierwirth) publie chaque saison la grille mondiale des émissions en ondes courtes :
  - sked-A26.csv (été : dernier dimanche de mars -> dernier dimanche d'octobre), sked-B26.csv (hiver
    2026/27) ; CSV « ; » : kHz;Time(UTC);Days;ITU;Station;Lng;Target;Remarks;P;Start;Stop;
    Time « 0000-2400 », Days vide = tous les jours, « 1245 » = lu, ma, je, ve (1 = lundi), « 24Oct »
    = ce jour-là ; Remarks = site d'émission : « t » (site t du pays de la station), « /D-r » (site r
    en Allemagne), « /D » (Allemagne, site principal), vide = site principal du pays ;
    Start / Stop = validité « jjmm », « [mmyy] » = date de dernière confirmation (ignorée).
  - README.TXT, partie « IV) Transmitter site codes » : « AUT: Moosbrunn 48N00-16E28 » (pays à un
    seul site) ou un en-tête de pays suivi de lignes « n-Nauen 52N38'55"-12E54'33" ».
Format relevé sur le serveur ORSAT le 21/10/2026. Les fichiers sont gardés dans data/eibi/.
"""

import logging
import re
import threading
import time
import urllib.request
from datetime import date, datetime, timedelta

from . import __version__
from .db import DATA_DIR

log = logging.getLogger("orsatlog.eibi")

BASE = "http://www.eibispace.de/dx/"
DIR = DATA_DIR / "eibi"
UA = f"ORSAT-LOG/{__version__} (F1NSK)"
REFRESH = 7 * 86400          # grille de la saison en cours relue chaque semaine
TOL_KHZ = 1.5                # écart toléré entre la fréquence notée et celle de la grille

_lock = threading.Lock()
_cache = {}                  # nom de fichier -> (mtime, données analysées)
_failed = {}                 # nom de fichier -> heure du dernier échec (on ne réessaie pas avant 6 h)


# ---------- saisons ----------
def _last_sunday(y, m):
    d = date(y, m + 1, 1) - timedelta(days=1) if m < 12 else date(y, 12, 31)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def season_of(d):
    """Saison EiBi d'une date : 'A26' (été 2026) ou 'B26' (hiver 2026/27)."""
    a0, b0 = _last_sunday(d.year, 3), _last_sunday(d.year, 10)
    if a0 <= d < b0:
        return f"A{d.year % 100:02d}"
    y = d.year if d >= b0 else d.year - 1
    return f"B{y % 100:02d}"


def previous_season(s):
    y = int(s[1:])
    return f"B{(y - 1) % 100:02d}" if s[0] == "A" else f"A{y:02d}"


# ---------- téléchargement ----------
def _download(name, max_age):
    path = DIR / name
    fresh = path.exists() and (max_age is None or time.time() - path.stat().st_mtime < max_age)
    if fresh:
        return path
    if time.time() - _failed.get(name, 0) < 6 * 3600:
        return path if path.exists() else None
    try:
        req = urllib.request.Request(BASE + name, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        if len(data) < 2000:
            raise ValueError("fichier trop court")
        DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        log.info("EiBi : %s téléchargé (%d octets)", name, len(data))
    except Exception as exc:
        _failed[name] = time.time()
        log.info("EiBi : %s indisponible (%s)", name, exc)
    return path if path.exists() else None


def _text(path):
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


# ---------- sites d'émission ----------
_COORD = re.compile(r"(\d{1,2})([NS])(\d{2})(?:'(\d{1,2}))?\"?-(\d{1,3})([EW])(\d{2})(?:'(\d{1,2}))?")
_HEAD = re.compile(r"^\s{0,6}([A-Z0-9]{1,4}):\s*(.*)$")
_SITE = re.compile(r"^([a-z0-9]{1,3})-(.+)$")


def _coord(text):
    m = _COORD.search(text)
    if not m:
        return None
    la = int(m[1]) + int(m[3]) / 60 + int(m[4] or 0) / 3600
    lo = int(m[5]) + int(m[7]) / 60 + int(m[8] or 0) / 3600
    return (round(-la if m[2] == "S" else la, 4), round(-lo if m[6] == "W" else lo, 4)), m.start()


def parse_sites(text):
    """{(pays ITU, code site ou ''): (nom, lat, lon)}"""
    lines = text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if "Transmitter site codes" in l)
    except StopIteration:
        return {}
    sites, country = {}, None
    for line in lines[start + 1:]:
        if re.match(r"^\s{0,4}V\)", line):          # partie suivante du README
            break
        if not line.strip():
            continue
        h = _HEAD.match(line)
        if h:
            country, rest = h[1], h[2].strip()
        elif country and line.startswith(" "):
            rest = line.strip()
        else:
            continue
        if not rest:
            continue
        s = _SITE.match(rest)
        code, body = (s[1], s[2]) if s else ("", rest)
        c = _coord(body)
        if not c:
            continue
        (la, lo), pos = c
        name = body[:pos].strip(" ,;:-")
        sites.setdefault((country, code), (name, la, lo))
    return sites


def _sites():
    p = _download("README.TXT", REFRESH)
    if not p:
        return {}
    key = "README.TXT"
    m = p.stat().st_mtime
    if key not in _cache or _cache[key][0] != m:
        _cache[key] = (m, parse_sites(_text(p)))
    return _cache[key][1]


def site_of(itu, remarks, sites):
    """Site d'émission d'une ligne de la grille -> (nom, lat, lon, pays) ou None."""
    r = (remarks or "").strip()
    country, code = itu, ""
    if r.startswith("/"):
        country, _, code = r[1:].partition("-")
    elif re.fullmatch(r"[a-z0-9]{1,3}", r):
        code = r
    hit = sites.get((country, code))
    if not hit and code:
        return None
    if not hit:
        hit = sites.get((country, ""))
    return (*hit, country) if hit else None


# ---------- grille ----------
_DAYNAMES = {"mo": 1, "tu": 2, "we": 3, "th": 4, "fr": 5, "sa": 6, "su": 7}
_MONTHS = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug",
                                            "sep", "oct", "nov", "dec"))}


def days_match(days, d):
    """Vrai si la colonne Days autorise la date d ; None si la grille ne le précise pas (irr…)."""
    s = (days or "").strip()
    if not s:
        return True
    wd = d.isoweekday()
    if s.isdigit():
        return str(wd) in s
    m = re.fullmatch(r"(\d{1,2})([A-Za-z]{3})", s)
    if m and m[2].lower() in _MONTHS:
        return d.day == int(m[1]) and d.month == _MONTHS[m[2].lower()]
    low = s.lower()
    m = re.fullmatch(r"([a-z]{2})-([a-z]{2})", low)
    if m and m[1] in _DAYNAMES and m[2] in _DAYNAMES:
        a, b = _DAYNAMES[m[1]], _DAYNAMES[m[2]]
        return a <= wd <= b if a <= b else (wd >= a or wd <= b)
    names = re.findall(r"[a-z]{2}", low)
    if names and all(n in _DAYNAMES for n in names) and re.fullmatch(r"[a-z,/ ]+", low):
        return wd in {_DAYNAMES[n] for n in names}
    return None


def _ddmm_ok(start, stop, d):
    def val(x):
        x = (x or "").strip()
        return (int(x[2:]), int(x[:2])) if re.fullmatch(r"\d{4}", x) else None
    a, b, k = val(start), val(stop), (d.month, d.day)
    if a and b:
        return a <= k <= b if a <= b else (k >= a or k <= b)
    if a:
        return k >= a
    if b:
        return k <= b
    return True


def _time_ok(span, hhmm):
    m = re.fullmatch(r"(\d{4})-(\d{4})", (span or "").strip())
    if not m:
        return None
    a, b = int(m[1]), int(m[2])
    return a <= hhmm < b if a < b else (hhmm >= a or hhmm < b)


def parse_sked(text):
    rows = []
    for line in text.splitlines()[1:]:
        f = line.split(";")
        if len(f) < 9:
            continue
        try:
            khz = float(f[0])
        except ValueError:
            continue
        rows.append((khz, f[1], f[2], f[3], f[4], f[5], f[6], f[7], f[9] if len(f) > 9 else "",
                     f[10] if len(f) > 10 else ""))
    rows.sort(key=lambda r: r[0])
    return rows


def _sked(season):
    name = f"sked-{season.lower()}.csv"
    p = _download(name, REFRESH)
    if not p:
        return None
    m = p.stat().st_mtime
    if name not in _cache or _cache[name][0] != m:
        _cache[name] = (m, parse_sked(_text(p)))
    return _cache[name][1]


def grid(d):
    """(saison, lignes) : grille de la saison de la date, sinon la plus récente disponible."""
    s = season_of(d)
    for cand in (s, previous_season(s)):
        rows = _sked(cand)
        if rows:
            return cand, rows
    return None, None


def latlon_to_locator(lat, lon):
    lon += 180
    lat += 90
    a = chr(65 + int(lon // 20)) + chr(65 + int(lat // 10))
    b = str(int((lon % 20) // 2)) + str(int(lat % 10))
    c = chr(97 + int((lon % 2) * 12)) + chr(97 + int((lat % 1) * 24))
    return (a + b + c).upper()


def lookup(freq_hz, qso_date, time_on, limit=8):
    """Stations de la grille EiBi sur cette fréquence à cette heure, les plus probables d'abord."""
    with _lock:
        d = datetime.strptime(qso_date, "%Y%m%d").date()
        season, rows = grid(d)
        if not rows:
            return {"ok": False, "msg": "Grille EiBi indisponible (serveur eibispace.de injoignable)."}
        sites = _sites()
    khz = freq_hz / 1000
    hhmm = int((time_on or "0000")[:4].ljust(4, "0"))
    out = []
    for r in rows:
        if r[0] < khz - TOL_KHZ:
            continue
        if r[0] > khz + TOL_KHZ:
            break
        t_ok = _time_ok(r[1], hhmm)
        if t_ok is False or not _ddmm_ok(r[8], r[9], d):
            continue
        dm = days_match(r[2], d)
        if dm is False:
            continue
        site = site_of(r[3], r[7], sites)
        out.append({
            "khz": r[0], "time": r[1], "days": r[2], "itu": r[3], "station": r[4].strip(),
            "lang": r[5].strip(), "target": r[6].strip(), "remarks": r[7].strip(),
            "site": site[0] if site else None,
            "site_country": site[3] if site else None,
            "lat": site[1] if site else None, "lon": site[2] if site else None,
            "locator": latlon_to_locator(site[1], site[2]) if site else None,
            "sure": dm is True and t_ok is True,
            # Une émission vers l'Europe (ou mondiale) est la plus probable à l'écoute en IN93
            "_score": abs(r[0] - khz) + (0 if dm is True else 0.5) + (0 if site else 0.2)
                      - (0.4 if re.search(r"Eu|Glo|Af", r[6]) else 0),
        })
    out.sort(key=lambda x: x["_score"])
    for x in out:
        x.pop("_score")
    cur = season_of(d)
    return {"ok": True, "season": season, "exact_season": season == cur, "candidates": out[:limit],
            "credit": "Grille EiBi (Eike Bierwirth), www.eibispace.de"}


def status():
    files = sorted(p.name for p in DIR.glob("*")) if DIR.exists() else []
    return {"files": files, "sites": len(_cache.get("README.TXT", (0, {}))[1])}
