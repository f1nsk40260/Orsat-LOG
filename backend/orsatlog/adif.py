"""ADIF 3.1 : export (carnet de trafic / journal d'écoute) et import (carnet de trafic seul)."""

import re
from datetime import datetime, timezone

from . import __version__
from .geo import ADIF_BANDS

# champ base -> champ ADIF
_MAP = [
    ("call", "CALL"), ("qso_date", "QSO_DATE"), ("time_on", "TIME_ON"),
    ("band", "BAND"), ("mode", "MODE"), ("submode", "SUBMODE"),
    ("rst_sent", "RST_SENT"), ("rst_rcvd", "RST_RCVD"), ("name", "NAME"),
    ("qth", "QTH"), ("gridsquare", "GRIDSQUARE"), ("comment", "COMMENT"),
    ("distance_km", "DISTANCE"), ("sfi", "SFI"), ("a_index", "A_INDEX"),
    ("k_index", "K_INDEX"),
]


def _field(tag, value):
    value = str(value)
    return f"<{tag}:{len(value.encode('utf-8'))}>{value} "


def export(qsos, my_call="", my_grid="", swl_grid="", kind="QSO"):
    """ADIF d'UN seul carnet : kind="QSO" = carnet de trafic (contacts, pour QRZ.com),
    kind="SWL" = journal d'écoute. Une entrée de l'autre type est toujours écartée."""
    qsos = [q for q in qsos if (q.get("kind") or "QSO") == kind]
    now = datetime.now(timezone.utc).strftime("%Y%m%d %H%M%S")
    out = [
        ("Export ORSAT-LOG - carnet de trafic\n" if kind == "QSO" else "Export ORSAT-LOG - journal d'écoute (SWL)\n"),
        _field("ADIF_VER", "3.1.4"),
        _field("PROGRAMID", "ORSAT-LOG"),
        _field("PROGRAMVERSION", __version__),
        _field("CREATED_TIMESTAMP", now),
        "<EOH>\n",
    ]
    for q in qsos:
        q = dict(q)
        if q.get("session_name"):   # QSO de groupe : nom repris dans le commentaire
            q["comment"] = f"[{q['session_name']}] {q.get('comment') or ''}".strip()
        rec = []
        for key, tag in _MAP:
            v = q.get(key)
            if key == "band" and v not in ADIF_BANDS:
                continue  # bande de radiodiffusion : pas de valeur ADIF, FREQ suffit
            if v not in (None, ""):
                rec.append(_field(tag, v))
        if q.get("session_name"):
            rec.append(_field("APP_ORSATLOG_SESSION", q["session_name"]))
            if q.get("session_animator"):
                rec.append(_field("APP_ORSATLOG_ANIMATOR", q["session_animator"]))
        if q.get("kind") == "SWL":
            rec.append(_field("SWL", "Y"))  # écoute (Short Wave Listener), pas un contact
        if q.get("freq"):
            rec.append(_field("FREQ", f"{q['freq'] / 1e6:.6f}"))
        if my_call:
            rec.append(_field("STATION_CALLSIGN", my_call))
        # MY_GRIDSQUARE : la station pour un QSO, le récepteur WebSDR pour une écoute SWL
        grid = (swl_grid or my_grid) if q.get("kind") == "SWL" else my_grid
        if grid:
            rec.append(_field("MY_GRIDSQUARE", grid))
        out.append("".join(rec) + "<EOR>\n")
    return "".join(out)


# ---------- import ----------
_TAG = re.compile(rb"<([A-Za-z0-9_]+)(?::(\d+)(?::[A-Za-z])?)?>")


def parse(data: bytes):
    """Lit un fichier ADIF (.adi) et renvoie la liste des enregistrements {CHAMP: valeur}.
    L'en-tête (avant <EOH>) est ignoré. Longueurs comptées en octets, comme notre export."""
    m = re.search(rb"<eoh>", data, re.IGNORECASE)
    pos = m.end() if m else 0
    if not m and not data.lstrip().startswith(b"<"):
        pos = len(data)          # texte d'en-tête sans <EOH> : rien à lire
    records, cur = [], {}
    while True:
        m = _TAG.search(data, pos)
        if not m:
            break
        tag = m.group(1).decode("ascii").upper()
        if tag == "EOR":
            if cur:
                records.append(cur)
            cur = {}
            pos = m.end()
            continue
        n = int(m.group(2) or 0)
        value = data[m.end():m.end() + n].decode("utf-8", errors="replace").strip()
        if value:
            cur[tag] = value
        pos = m.end() + n
    return records


def to_entry(rec):
    """Enregistrement ADIF -> entrée du carnet de trafic (champs de la base), ou None si
    l'enregistrement n'est pas un contact exploitable. Renvoie (entrée, motif du refus)."""
    if rec.get("SWL", "").upper() == "Y":
        return None, "écoute (SWL)"
    call = rec.get("CALL", "").strip().upper()
    date = re.sub(r"\D", "", rec.get("QSO_DATE", ""))
    time_on = re.sub(r"\D", "", rec.get("TIME_ON", ""))
    if not call or len(date) != 8:
        return None, "indicatif ou date manquant"
    if len(time_on) == 4:
        time_on += "00"
    if len(time_on) != 6:
        return None, "heure manquante"
    try:
        datetime.strptime(date + time_on, "%Y%m%d%H%M%S")
    except ValueError:
        return None, "date ou heure invalide"
    freq = None
    try:
        if rec.get("FREQ"):
            freq = round(float(rec["FREQ"].replace(",", ".")) * 1e6)
    except ValueError:
        freq = None
    return {
        "kind": "QSO", "call": call, "qso_date": date, "time_on": time_on, "freq": freq,
        "band": rec.get("BAND", "").lower(),
        "mode": rec.get("MODE", "").upper(), "submode": rec.get("SUBMODE", "").upper(),
        "rst_sent": rec.get("RST_SENT", ""), "rst_rcvd": rec.get("RST_RCVD", ""),
        "name": rec.get("NAME", ""), "qth": rec.get("QTH", ""),
        "gridsquare": rec.get("GRIDSQUARE", "").upper(),
        "comment": rec.get("COMMENT", "") or rec.get("NOTES", ""),
    }, ""
