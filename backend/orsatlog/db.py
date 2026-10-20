"""Base SQLite du carnet : QSO / écoutes SWL, relevés de propagation, notes du jour, réglages."""

import json
import logging
import os
import sqlite3
import threading
from pathlib import Path

# Données dans le dossier d'ORSAT-LOG lui-même : ~/Orsat-LOG/data (ignoré par git).
# ORSATLOG_DATA permet toujours de choisir un autre dossier.
ROOT = Path(__file__).resolve().parents[2]
OLD_DATA_DIR = Path.home() / ".local/share/orsat-log"      # emplacement jusqu'à la v0.6.4
DATA_DIR = Path(os.environ.get("ORSATLOG_DATA", ROOT / "data"))
DB_PATH = DATA_DIR / "orsatlog.db"


def _migrate_old_db():
    """Reprend la base de l'ancien emplacement au premier lancement. L'ancienne est
    renommée orsatlog.db.ancien (copie de sécurité), jamais supprimée."""
    old = OLD_DATA_DIR / "orsatlog.db"
    if "ORSATLOG_DATA" in os.environ or DB_PATH.exists() or not old.exists():
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(old)
    try:
        dst = sqlite3.connect(DB_PATH)
        src.backup(dst)          # copie cohérente, journal WAL compris
        dst.close()
    finally:
        src.close()
    old.rename(old.with_name("orsatlog.db.ancien"))
    logging.getLogger("orsatlog").info("Base déplacée de %s vers %s", old, DB_PATH)


_migrate_old_db()

DEFAULT_SETTINGS = {
    "callsign": "",
    "locator": "",
    "tci_host": "127.0.0.1",
    "tci_port": "50001",
    "tci_trx": "0",
    "tci_enabled": "1",
    "websdr_port": "40001",
    "websdr_enabled": "1",
    "weathercloud": "9224966553",   # identifiant de la station Weathercloud (F1NSK - Castets)
}

QSO_FIELDS = [
    "kind", "session_id", "call", "qso_date", "time_on", "freq", "band", "mode", "submode",
    "rst_sent", "rst_rcvd", "name", "qth", "gridsquare", "comment",
    "distance_km", "bearing", "sfi", "a_index", "k_index",
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS qso (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    call        TEXT NOT NULL,
    qso_date    TEXT NOT NULL,      -- AAAAMMJJ (UTC)
    time_on     TEXT NOT NULL,      -- HHMMSS (UTC)
    freq        INTEGER,            -- Hz
    band        TEXT,
    mode        TEXT,
    submode     TEXT,
    rst_sent    TEXT,
    rst_rcvd    TEXT,
    name        TEXT,
    qth         TEXT,
    gridsquare  TEXT,
    comment     TEXT,
    -- contexte propagation, figé au moment du QSO
    distance_km INTEGER,
    bearing     INTEGER,
    sfi         REAL,
    a_index     REAL,
    k_index     REAL,
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_qso_call ON qso(call);
CREATE INDEX IF NOT EXISTS idx_qso_date ON qso(qso_date, time_on);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
-- relevés de propagation pris au fil de la journée
CREATE TABLE IF NOT EXISTS propagation (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    day         TEXT NOT NULL,      -- AAAAMMJJ (UTC)
    time        TEXT NOT NULL,      -- HHMMSS (UTC)
    source      TEXT,               -- ex. hamqsl
    source_time TEXT,               -- horodatage annoncé par la source
    sfi         REAL,
    a_index     REAL,
    k_index     REAL,
    sunspots    REAL,
    xray        TEXT,
    geomagfield TEXT,
    conditions  TEXT                -- JSON : état des bandes jour/nuit
);
CREATE INDEX IF NOT EXISTS idx_prop_day ON propagation(day, time);
-- relevés météo de la station locale
CREATE TABLE IF NOT EXISTS weather (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    day       TEXT NOT NULL,        -- AAAAMMJJ (UTC)
    time      TEXT NOT NULL,        -- HHMMSS (UTC) de la mesure
    epoch     INTEGER,
    temp      REAL,                 -- °C
    hum       REAL,                 -- %
    dew       REAL,                 -- °C
    bar       REAL,                 -- hPa
    wspd      REAL,                 -- km/h
    wspdhi    REAL,                 -- km/h (rafale)
    wdir      REAL,                 -- degrés
    rain      REAL,                 -- mm depuis minuit
    rainrate  REAL,                 -- mm/h
    solarrad  REAL,                 -- W/m²
    uvi       REAL
);
CREATE INDEX IF NOT EXISTS idx_weather_day ON weather(day, time);
-- QSO de groupe (table ronde, « QSO des Copains ») : un nom, un créneau, une fréquence
CREATE TABLE IF NOT EXISTS session (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    day         TEXT NOT NULL,      -- AAAAMMJJ (UTC)
    name        TEXT NOT NULL,
    time_start  TEXT NOT NULL,      -- HHMM (UTC)
    time_end    TEXT,               -- HHMM (UTC), vide = en cours
    freq        INTEGER,
    mode        TEXT,
    submode     TEXT,
    animator    TEXT,               -- indicatif de l'animateur (station qui mène la ronde)
    comment     TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_session_day ON session(day, time_start);
CREATE INDEX IF NOT EXISTS idx_session_name ON session(name);
-- noms de QSO de groupe préenregistrés, avec leurs réglages habituels
CREATE TABLE IF NOT EXISTS group_template (
    name        TEXT PRIMARY KEY COLLATE NOCASE,
    time_start  TEXT,
    time_end    TEXT,
    freq        INTEGER,
    mode        TEXT,
    submode     TEXT,
    animator    TEXT,
    updated_at  TEXT DEFAULT (datetime('now'))
);
-- page d'agenda : notes libres du jour
CREATE TABLE IF NOT EXISTS day_note (
    day        TEXT PRIMARY KEY,
    text       TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);
"""


class Database:
    def __init__(self, path=DB_PATH):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._con = sqlite3.connect(str(path), check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        self._con.executescript(_SCHEMA)
        # migration v0.2 -> v0.3 : type d'entrée QSO / SWL
        cols = [r["name"] for r in self._con.execute("PRAGMA table_info(qso)")]
        if "kind" not in cols:
            self._con.execute("ALTER TABLE qso ADD COLUMN kind TEXT NOT NULL DEFAULT 'QSO'")
        # migration v0.4 -> v0.5 : rattachement à un QSO de groupe
        if "session_id" not in cols:
            self._con.execute("ALTER TABLE qso ADD COLUMN session_id INTEGER")
        self._con.execute("CREATE INDEX IF NOT EXISTS idx_qso_session ON qso(session_id)")
        # migration v0.5 -> v0.6 : animateur du QSO de groupe
        scols = [r["name"] for r in self._con.execute("PRAGMA table_info(session)")]
        if "animator" not in scols:
            self._con.execute("ALTER TABLE session ADD COLUMN animator TEXT")
        # migration v0.5 -> v0.6 : noms préenregistrés repris des sessions existantes
        if self._con.execute("SELECT COUNT(*) FROM group_template").fetchone()[0] == 0:
            self._con.execute(
                "INSERT OR IGNORE INTO group_template(name, time_start, time_end, freq, mode, submode, animator) "
                "SELECT s.name, s.time_start, s.time_end, s.freq, s.mode, s.submode, s.animator FROM session s "
                "WHERE s.id IN (SELECT MAX(id) FROM session GROUP BY name)")
        # migration v0.1 -> v0.2 : port TCI par défaut 40001 -> 50001 (AetherSDR)
        if self._con.execute("SELECT 1 FROM settings WHERE key = 'tci_trx'").fetchone() is None:
            self._con.execute("UPDATE settings SET value = '50001' WHERE key = 'tci_port' AND value = '40001'")
        for k, v in DEFAULT_SETTINGS.items():
            self._con.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
        self._con.commit()

    # --- réglages ---
    def get_settings(self):
        with self._lock:
            rows = self._con.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}

    def set_settings(self, values):
        with self._lock:
            for k, v in values.items():
                if k in DEFAULT_SETTINGS:
                    self._con.execute(
                        "INSERT INTO settings(key, value) VALUES (?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        (k, str(v)),
                    )
            self._con.commit()

    # --- QSO ---
    def add_qso(self, qso):
        cols = [f for f in QSO_FIELDS if f in qso]
        with self._lock:
            cur = self._con.execute(
                f"INSERT INTO qso({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                [qso[c] for c in cols],
            )
            self._con.commit()
            return self.get_qso(cur.lastrowid, _locked=True)

    def get_qso(self, qso_id, _locked=False):
        sql = "SELECT q.*, s.name AS session_name, s.animator AS session_animator FROM qso q LEFT JOIN session s ON s.id = q.session_id WHERE q.id = ?"
        if _locked:
            row = self._con.execute(sql, (qso_id,)).fetchone()
        else:
            with self._lock:
                row = self._con.execute(sql, (qso_id,)).fetchone()
        return dict(row) if row else None

    def list_qsos(self, limit=200):
        with self._lock:
            rows = self._con.execute(
                "SELECT q.*, s.name AS session_name, s.animator AS session_animator FROM qso q LEFT JOIN session s ON s.id = q.session_id ORDER BY q.qso_date DESC, q.time_on DESC, q.id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def all_qsos(self):
        with self._lock:
            rows = self._con.execute("SELECT q.*, s.name AS session_name, s.animator AS session_animator FROM qso q LEFT JOIN session s ON s.id = q.session_id ORDER BY q.qso_date, q.time_on, q.id").fetchall()
        return [dict(r) for r in rows]

    def worked_before(self, call):
        with self._lock:
            rows = self._con.execute(
                "SELECT qso_date, time_on, band, mode FROM qso WHERE call = ? AND kind = 'QSO' "
                "ORDER BY qso_date DESC, time_on DESC LIMIT 20",
                (call.upper(),),
            ).fetchall()
        return [dict(r) for r in rows]

    def update_qso(self, qso_id, qso):
        cols = [f for f in QSO_FIELDS if f in qso]
        with self._lock:
            cur = self._con.execute(
                f"UPDATE qso SET {', '.join(f'{c} = ?' for c in cols)} WHERE id = ?",
                [qso[c] for c in cols] + [qso_id],
            )
            self._con.commit()
            return self.get_qso(qso_id, _locked=True) if cur.rowcount else None

    def delete_qso(self, qso_id):
        with self._lock:
            cur = self._con.execute("DELETE FROM qso WHERE id = ?", (qso_id,))
            self._con.commit()
            return cur.rowcount > 0

    # --- agenda : une page par jour UTC ---
    def day_qsos(self, day):
        with self._lock:
            rows = self._con.execute(
                "SELECT q.*, s.name AS session_name, s.animator AS session_animator FROM qso q LEFT JOIN session s ON s.id = q.session_id WHERE q.qso_date = ? ORDER BY q.time_on DESC, q.id DESC", (day,)
            ).fetchall()
        return [dict(r) for r in rows]

    def add_snapshot(self, day, time, data, source="hamqsl"):
        with self._lock:
            self._con.execute(
                "INSERT INTO propagation(day, time, source, source_time, sfi, a_index, k_index, "
                "sunspots, xray, geomagfield, conditions) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (day, time, source, data.get("updated"), data.get("sfi"), data.get("a_index"),
                 data.get("k_index"), data.get("sunspots"), data.get("xray"),
                 data.get("geomagfield"), json.dumps(data.get("conditions") or [])),
            )
            self._con.commit()

    def last_snapshot(self):
        with self._lock:
            row = self._con.execute("SELECT * FROM propagation ORDER BY day DESC, time DESC, id DESC LIMIT 1").fetchone()
        return self._snap(row) if row else None

    def day_snapshots(self, day):
        with self._lock:
            rows = self._con.execute(
                "SELECT * FROM propagation WHERE day = ? ORDER BY time", (day,)
            ).fetchall()
        return [self._snap(r) for r in rows]

    @staticmethod
    def _snap(row):
        d = dict(row)
        try:
            d["conditions"] = json.loads(d.get("conditions") or "[]")
        except ValueError:
            d["conditions"] = []
        return d

    def get_note(self, day):
        with self._lock:
            row = self._con.execute("SELECT text FROM day_note WHERE day = ?", (day,)).fetchone()
        return row["text"] if row else ""

    def set_note(self, day, text):
        with self._lock:
            if text.strip():
                self._con.execute(
                    "INSERT INTO day_note(day, text) VALUES (?, ?) ON CONFLICT(day) DO UPDATE "
                    "SET text = excluded.text, updated_at = datetime('now')", (day, text))
            else:
                self._con.execute("DELETE FROM day_note WHERE day = ?", (day,))
            self._con.commit()

    def month_activity(self, month):
        """Activité de chaque jour du mois AAAAMM : nombre de QSO, d'écoutes SWL, note présente."""
        like = f"{month}%"
        out = {}
        with self._lock:
            for r in self._con.execute(
                "SELECT qso_date AS day, SUM(kind = 'QSO') AS qso, SUM(kind = 'SWL') AS swl "
                "FROM qso WHERE qso_date LIKE ? GROUP BY qso_date", (like,)):
                out[r["day"]] = {"qso": r["qso"], "swl": r["swl"], "note": False}
            for r in self._con.execute("SELECT day FROM day_note WHERE day LIKE ?", (like,)):
                out.setdefault(r["day"], {"qso": 0, "swl": 0})["note"] = True
        return out

    # --- météo ---
    WEATHER_FIELDS = ["temp", "hum", "dew", "bar", "wspd", "wspdhi", "wdir", "rain", "rainrate", "solarrad", "uvi"]

    def add_weather(self, day, time, data):
        cols = ["day", "time", "epoch"] + self.WEATHER_FIELDS
        vals = [day, time, data.get("epoch")] + [data.get(f) for f in self.WEATHER_FIELDS]
        with self._lock:
            self._con.execute(
                f"INSERT INTO weather({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", vals)
            self._con.commit()

    def last_weather(self):
        with self._lock:
            row = self._con.execute(
                "SELECT * FROM weather ORDER BY day DESC, time DESC, id DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def day_weather(self, day):
        with self._lock:
            rows = self._con.execute("SELECT * FROM weather WHERE day = ? ORDER BY time", (day,)).fetchall()
        return [dict(r) for r in rows]

    # --- QSO de groupe ---
    SESSION_FIELDS = ["name", "time_start", "time_end", "freq", "mode", "submode", "animator", "comment"]

    def create_session(self, day, data):
        cols = ["day"] + [f for f in self.SESSION_FIELDS if f in data]
        with self._lock:
            cur = self._con.execute(
                f"INSERT INTO session({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                [day] + [data[c] for c in cols[1:]])
            self._con.commit()
        return self.get_session(cur.lastrowid)

    def update_session(self, sid, data):
        cols = [f for f in self.SESSION_FIELDS if f in data]
        if cols:
            with self._lock:
                self._con.execute(f"UPDATE session SET {', '.join(c + ' = ?' for c in cols)} WHERE id = ?",
                                  [data[c] for c in cols] + [sid])
                self._con.commit()
        return self.get_session(sid)

    def get_session(self, sid):
        with self._lock:
            row = self._con.execute(
                "SELECT s.*, (SELECT COUNT(*) FROM qso WHERE session_id = s.id) AS count "
                "FROM session s WHERE s.id = ?", (sid,)).fetchone()
        return dict(row) if row else None

    def day_sessions(self, day):
        with self._lock:
            rows = self._con.execute(
                "SELECT s.*, (SELECT COUNT(*) FROM qso WHERE session_id = s.id) AS count "
                "FROM session s WHERE s.day = ? ORDER BY s.time_start", (day,)).fetchall()
        return [dict(r) for r in rows]

    def session_qsos(self, sid):
        with self._lock:
            rows = self._con.execute(
                "SELECT * FROM qso WHERE session_id = ? ORDER BY time_on, id", (sid,)).fetchall()
        return [dict(r) for r in rows]

    def delete_session(self, sid):
        """Supprime la session et les QSO qui lui sont rattachés."""
        with self._lock:
            self._con.execute("DELETE FROM qso WHERE session_id = ?", (sid,))
            cur = self._con.execute("DELETE FROM session WHERE id = ?", (sid,))
            self._con.commit()
            return cur.rowcount > 0

    TEMPLATE_FIELDS = ["time_start", "time_end", "freq", "mode", "submode", "animator"]

    def session_names(self):
        """Noms de QSO de groupe préenregistrés + réglages habituels + nombre de sessions tenues."""
        with self._lock:
            rows = self._con.execute(
                "SELECT t.*, (SELECT COUNT(*) FROM session s WHERE s.name = t.name COLLATE NOCASE) AS cnt, "
                "(SELECT MAX(day) FROM session s WHERE s.name = t.name COLLATE NOCASE) AS day "
                "FROM group_template t ORDER BY t.time_start, t.name").fetchall()
        return [dict(r) for r in rows]

    def upsert_template(self, name, data):
        cols = [f for f in self.TEMPLATE_FIELDS if f in data]
        with self._lock:
            self._con.execute("INSERT OR IGNORE INTO group_template(name) VALUES (?)", (name,))
            if cols:
                self._con.execute(
                    f"UPDATE group_template SET {', '.join(c + ' = ?' for c in cols)}, updated_at = datetime('now') "
                    "WHERE name = ?", [data[c] for c in cols] + [name])
            self._con.commit()

    def delete_template(self, name):
        with self._lock:
            cur = self._con.execute("DELETE FROM group_template WHERE name = ?", (name,))
            self._con.commit()
            return cur.rowcount > 0

    def regulars(self, name, last_sessions=10):
        """Habitués d'un QSO de groupe : stations présentes dans les dernières sessions du même nom,
        avec les nom / QTH / locator de leur dernier passage."""
        with self._lock:
            rows = self._con.execute(
                """SELECT q.call, COUNT(DISTINCT q.session_id) AS times,
                          (SELECT q2.name FROM qso q2 WHERE q2.call = q.call AND q2.name != '' ORDER BY q2.id DESC LIMIT 1) AS name,
                          (SELECT q2.qth FROM qso q2 WHERE q2.call = q.call AND q2.qth != '' ORDER BY q2.id DESC LIMIT 1) AS qth,
                          (SELECT q2.gridsquare FROM qso q2 WHERE q2.call = q.call AND q2.gridsquare != '' ORDER BY q2.id DESC LIMIT 1) AS gridsquare
                   FROM qso q
                   WHERE q.session_id IN (SELECT id FROM session WHERE name = ? ORDER BY day DESC, time_start DESC LIMIT ?)
                   GROUP BY q.call ORDER BY times DESC, q.call""",
                (name, last_sessions)).fetchall()
        return [dict(r) for r in rows]
