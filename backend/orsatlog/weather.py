"""Météo locale depuis une station Weathercloud (app.weathercloud.net).

Adresse non officielle utilisée par le site lui-même :
    GET https://app.weathercloud.net/device/values?code=<identifiant à 10 chiffres>
    en-tête X-Requested-With: XMLHttpRequest + cookie de session du site
Le cookie est obtenu automatiquement en ouvrant d'abord la page de la station.
Champs : temp, hum, dew, chill, bar (hPa), wspd / wspdavg / wspdhi (m/s), wdir, rain (mm du jour),
rainrate (mm/h), solarrad (W/m²), uvi, epoch (heure de la mesure, secondes Unix).
"""

import http.cookiejar
import json
import logging
import re
import time
import urllib.error
import urllib.request

log = logging.getLogger("orsatlog.weather")

BASE = "https://app.weathercloud.net"
UA = "Mozilla/5.0 (X11; Linux x86_64) ORSAT-LOG"
CACHE_SECONDS = 5 * 60

_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))
_cache = {"code": None, "t": 0.0, "data": None, "error": ""}


def parse_code(value):
    """Accepte l'identifiant seul ou l'adresse de la station (…/d9224966553#current)."""
    m = re.search(r"(\d{10})", value or "")
    return m.group(1) if m else ""


def _get(url, ajax=False):
    headers = {"User-Agent": UA}
    if ajax:
        headers.update({
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": url.split("/device")[0],
        })
    req = urllib.request.Request(url, headers=headers)
    with _opener.open(req, timeout=10) as resp:
        return resp.read().decode("utf-8", "replace")


def _num(v):
    try:
        return round(float(v), 1)
    except (TypeError, ValueError):
        return None


def _fetch(code):
    page = f"{BASE}/d{code}"
    if not any(c.domain.endswith("weathercloud.net") for c in _jar):
        _get(page)  # récupère le cookie de session
    body = _get(f"{BASE}/device/values?code={code}", ajax=True).strip()
    if not body or body == "null":
        _jar.clear()  # cookie expiré ? nouvel essai complet
        _get(page)
        body = _get(f"{BASE}/device/values?code={code}", ajax=True).strip()
    if not body or body == "null":
        raise ValueError("aucune donnée renvoyée (station hors ligne ?)")
    raw = json.loads(body)
    if not isinstance(raw, dict) or "error" in raw:
        raise ValueError(f"réponse Weathercloud inattendue : {body[:80]}")
    ms_to_kmh = lambda v: None if v is None else round(v * 3.6, 1)
    return {
        "epoch": int(raw["epoch"]) if raw.get("epoch") else None,
        "temp": _num(raw.get("temp")),
        "hum": _num(raw.get("hum")),
        "dew": _num(raw.get("dew")),
        "chill": _num(raw.get("chill")),
        "bar": _num(raw.get("bar")),
        "wspd": ms_to_kmh(_num(raw.get("wspd"))),
        "wspdavg": ms_to_kmh(_num(raw.get("wspdavg"))),
        "wspdhi": ms_to_kmh(_num(raw.get("wspdhi"))),
        "wdir": _num(raw.get("wdir")),
        "rain": _num(raw.get("rain")),
        "rainrate": _num(raw.get("rainrate")),
        "solarrad": _num(raw.get("solarrad")),
        "uvi": _num(raw.get("uvi")),
    }


def get_weather(code_or_url):
    """Dernières mesures de la station (dict) ou None. Bloquant : appeler via to_thread.
    La dernière erreur est disponible dans last_error()."""
    code = parse_code(code_or_url)
    if not code:
        _cache.update(code=None, data=None, error="identifiant Weathercloud non renseigné")
        return None
    now = time.time()
    if _cache["code"] != code:
        _cache.update(code=code, t=0.0, data=None)
    if now - _cache["t"] > CACHE_SECONDS:   # au plus une requête toutes les 5 min, même en erreur
        try:
            _cache["data"] = _fetch(code)
            _cache["error"] = ""
        except Exception as exc:
            log.info("Weathercloud %s : %s", code, exc)
            _cache["error"] = _explain(exc)
        _cache["t"] = now
    return _cache["data"]


def _explain(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return f"le site a répondu une erreur {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        return "site injoignable (connexion réseau ?)"
    if isinstance(exc, json.JSONDecodeError):
        return "réponse illisible (format du site modifié ?)"
    return str(exc)[:120]


def last_error():
    return _cache["error"]
