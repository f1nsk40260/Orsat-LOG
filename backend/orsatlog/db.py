"""Base SQLite du carnet : QSO / écoutes SWL, relevés de propagation, notes du jour, réglages."""

import json
import os
import sqlite3
import threading
from pathlib import Path

DATA_DIR = Path(os.environ.get("ORSATLOG_DATA", Path.home() / ".local/share/orsat-log"))
DB_PATH = DATA_DIR / "orsatlog.db"

DEFAULT_SETTINGS = {
    "callsign": "",
    "locator": "",
    "tci_host": "127.0.0.1",
    "tci_port": "50001",
    "tci_trx": "0",
    "tci_enabled": "1",
}

QSO_FIELDS = [
    "kind", "call", "qso_date", "time_on", "freq", "band", "mode", "submode",
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
        sql = "SELECT * FROM qso WHERE id = ?"
        if _locked:
            row = self._con.execute(sql, (qso_id,)).fetchone()
        else:
            with self._lock:
                row = self._con.execute(sql, (qso_id,)).fetchone()
        return dict(row) if row else None

    def list_qsos(self, limit=200):
        with self._lock:
            rows = self._con.execute(
                "SELECT * FROM qso ORDER BY qso_date DESC, time_on DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def all_qsos(self):
        with self._lock:
            rows = self._con.execute("SELECT * FROM qso ORDER BY qso_date, time_on, id").fetchall()
        return [dict(r) for r in rows]

    def worked_before(self, call):
        with self._lock:
            rows = self._con.execute(
                "SELECT qso_date, time_on, band, mode FROM qso WHERE call = ? AND kind = 'QSO' "
                "ORDER BY qso_date DESC, time_on DESC LIMIT 20",
                (call.upper(),),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_qso(self, qso_id):
        with self._lock:
            cur = self._con.execute("DELETE FROM qso WHERE id = ?", (qso_id,))
            self._con.commit()
            return cur.rowcount > 0

    # --- agenda : une page par jour UTC ---
    def day_qsos(self, day):
        with self._lock:
            rows = self._con.execute(
                "SELECT * FROM qso WHERE qso_date = ? ORDER BY time_on DESC, id DESC", (day,)
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
