"""Export ADIF 3.1."""

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


def export(qsos, my_call="", my_grid=""):
    now = datetime.now(timezone.utc).strftime("%Y%m%d %H%M%S")
    out = [
        "Export ORSAT-LOG\n",
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
        if my_grid:
            rec.append(_field("MY_GRIDSQUARE", my_grid))
        out.append("".join(rec) + "<EOR>\n")
    return "".join(out)
