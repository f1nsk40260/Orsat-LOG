"""Locators Maidenhead, distances, azimuts et bandes."""

import math
import re

_LOC_RE = re.compile(r"^[A-R]{2}[0-9]{2}([A-X]{2}([0-9]{2})?)?$")

# (nom ADIF, f_min Hz, f_max Hz)
BANDS = [
    ("2190m", 135_700, 137_800),
    ("630m", 472_000, 479_000),
    ("160m", 1_800_000, 2_000_000),
    ("80m", 3_500_000, 4_000_000),
    ("60m", 5_060_000, 5_450_000),
    ("40m", 7_000_000, 7_300_000),
    ("30m", 10_100_000, 10_150_000),
    ("20m", 14_000_000, 14_350_000),
    ("17m", 18_068_000, 18_168_000),
    ("15m", 21_000_000, 21_450_000),
    ("12m", 24_890_000, 24_990_000),
    ("10m", 28_000_000, 29_700_000),
    ("6m", 50_000_000, 54_000_000),
    ("4m", 70_000_000, 71_000_000),
    ("2m", 144_000_000, 148_000_000),
    ("70cm", 420_000_000, 450_000_000),
    ("13cm", 2_300_000_000, 2_450_000_000),
]


def band_of(freq_hz):
    if not freq_hz:
        return ""
    for name, lo, hi in BANDS:
        if lo <= freq_hz <= hi:
            return name
    return ""


def valid_locator(loc):
    return bool(loc) and bool(_LOC_RE.match(loc.upper()))


def locator_to_latlon(loc):
    """Centre du carré locator (4, 6 ou 8 caractères) -> (lat, lon) en degrés."""
    loc = loc.strip().upper()
    if not valid_locator(loc):
        raise ValueError(f"locator invalide : {loc}")
    lon = (ord(loc[0]) - 65) * 20 - 180
    lat = (ord(loc[1]) - 65) * 10 - 90
    lon += int(loc[2]) * 2
    lat += int(loc[3])
    w_lon, w_lat = 2.0, 1.0
    if len(loc) >= 6:
        lon += (ord(loc[4]) - 65) * (2 / 24)
        lat += (ord(loc[5]) - 65) * (1 / 24)
        w_lon, w_lat = 2 / 24, 1 / 24
    if len(loc) == 8:
        lon += int(loc[6]) * (2 / 240)
        lat += int(loc[7]) * (1 / 240)
        w_lon, w_lat = 2 / 240, 1 / 240
    return lat + w_lat / 2, lon + w_lon / 2


def distance_bearing(loc_a, loc_b):
    """Distance orthodromique (km) et azimut (degrés) de A vers B."""
    lat1, lon1 = map(math.radians, locator_to_latlon(loc_a))
    lat2, lon2 = map(math.radians, locator_to_latlon(loc_b))
    dlon = lon2 - lon1
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    dist = 2 * 6371.0 * math.asin(min(1.0, math.sqrt(a)))
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    brg = (math.degrees(math.atan2(y, x)) + 360) % 360
    return round(dist), round(brg)
