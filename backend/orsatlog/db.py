"""Base SQLite du carnet : QSO + réglages."""

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
    "call", "qso_date", "time_on", "freq", "band", "mode", "submode",
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
"""


class Database:
    def __init__(self, path=DB_PATH):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._con = sqlite3.connect(str(path), check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        self._con.executescript(_SCHEMA)
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
                "SELECT qso_date, time_on, band, mode FROM qso WHERE call = ? "
                "ORDER BY qso_date DESC, time_on DESC LIMIT 20",
                (call.upper(),),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_qso(self, qso_id):
        with self._lock:
            cur = self._con.execute("DELETE FROM qso WHERE id = ?", (qso_id,))
            self._con.commit()
            return cur.rowcount > 0
