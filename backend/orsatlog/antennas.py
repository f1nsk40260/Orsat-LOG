"""Antenne de réception du WebSDR ORSAT (diagramme NEC réel) et angle de départ d'un saut F2.

Sert à la carte d'écoute du WebSDR (reach.listen_map).
"""

import math

EARTH_R = 6371.0
H_F2 = 300.0


def takeoff_deg(d_km):
    """Angle de départ d'un saut de d km (réflexion F2 à 300 km), un seul saut jusqu'à 3500 km."""
    n = max(1, math.ceil(d_km / 3500))
    theta = (d_km / n) / (2 * EARTH_R)
    return math.degrees(math.atan((math.cos(theta) - EARTH_R / (EARTH_R + H_F2)) / math.sin(theta)))



# ---------- antenne du WebSDR ORSAT : diagramme NEC réel ----------
# websdr_loop.json : loop horizontale 80 m (trapèze) à 6 m sur sable, alimentée dans un angle (balun 4:1),
# NEC-2 avec sol de Sommerfeld ; désadaptation calculée par rapport à 200 Ω.
# « avg » = gain moyenné sur l'azimut par degré d'élévation ; « grid » = [élévation][azimut tous les 5°]
# (orientation de la loop encore inconnue : on utilise la moyenne).
_WEBSDR = None


def websdr_pattern():
    global _WEBSDR
    if _WEBSDR is None:
        import json
        from pathlib import Path
        _WEBSDR = json.loads((Path(__file__).with_name("websdr_loop.json")).read_text())
    return _WEBSDR


def websdr_gain(band, elev_deg):
    """Gain de réception (dBi, moyenne azimut) de la loop du WebSDR ; bande sans calcul -> la plus proche."""
    pat = websdr_pattern()["bands"]
    if band not in pat:
        mhz = {"6m": 50.0}.get(band)
        band = min(pat, key=lambda b: abs(pat[b]["mhz"] - (mhz or 0)))
    e = max(0, min(90, int(round(elev_deg))))
    # pénalité de rapport signal/bruit due à la désadaptation (nulle tant que le bruit extérieur domine)
    return pat[band]["avg"][e] - pat[band].get("snr_penalty_db", 0.0)
