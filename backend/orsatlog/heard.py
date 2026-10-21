"""Ce que le WebSDR entendait : stations FT8 / FT4 / JS8 / WSPR décodées par l'autorun de
PhantomSDR-ORSAT, devenues des observations de propagation.

L'autorun écrit chaque station décodée dans <PhantomSDR>/autorun-spots/AAAAMMJJ-HH.jsonl
(autorun/spool.js) : {"t": unix, "mode", "band", "call", "grid", "snr", "f": Hz[, "dbm"]}.
Le carnet relit ces fichiers chaque minute (position mémorisée), puis efface ceux qui sont lus et
terminés. Deux niveaux :
  - heard      : détail, une ligne par station, bande, mode et heure UTC (meilleur SNR, nombre de
                 décodages) ; gardé HEARD_DAYS jours dans la limite de HEARD_MAX_ROWS lignes
                 (FIFO : les jours les plus anciens partent d'abord) ;
  - heard_sum  : résumé par jour, heure, bande et secteur de direction (8 secteurs depuis le
                 WebSDR) : nombre de stations, distance maximale ; gardé pour toujours.
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import auth, geo

log = logging.getLogger("orsatlog.heard")

SPOOL = Path(os.environ.get("ORSATLOG_SPOTS_DIR", str(auth.ADMIN_CONFIG.parent / "autorun-spots")))
HEARD_DAYS = 730                 # 2 ans de détail
HEARD_MAX_ROWS = 14_000_000      # ~2 Go de base au plus pour le détail (~150 o par ligne indexée)
SECTORS = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS heard (
    day TEXT NOT NULL, hour INTEGER NOT NULL, band TEXT NOT NULL, mode TEXT NOT NULL,
    call TEXT NOT NULL, grid TEXT, snr INTEGER, n INTEGER DEFAULT 1, first_t INTEGER, last_t INTEGER,
    freq INTEGER, lat REAL, lon REAL, km INTEGER, bearing INTEGER,
    PRIMARY KEY (day, hour, band, mode, call)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS heard_sum (
    day TEXT NOT NULL, hour INTEGER NOT NULL, band TEXT NOT NULL, sector TEXT NOT NULL,
    stations INTEGER, max_km INTEGER, max_call TEXT,
    PRIMARY KEY (day, hour, band, sector)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS heard_spool (name TEXT PRIMARY KEY, pos INTEGER);
"""


def sector_of(bearing):
    if bearing is None:
        return "?"
    return SECTORS[int(((bearing % 360) + 22.5) // 45) % 8]


class Heard:
    def __init__(self, db):
        self.db = db
        with db._lock:
            db._con.executescript(_SCHEMA)
            db._con.commit()
        self.last_ingest = None
        self.last_count = 0

    # ---------- lecture du journal de l'autorun ----------
    def _home(self):
        s = self.db.get_settings()
        loc = s.get("swl_locator") or s.get("locator") or ""
        return geo.locator_to_latlon(loc) if geo.valid_locator(loc) else None

    def ingest(self):
        """Relit les fichiers de l'autorun ; renvoie le nombre de décodages lus."""
        if not SPOOL.is_dir():
            return 0
        home = self._home()
        names = sorted(n for n in os.listdir(SPOOL) if re.fullmatch(r"\d{8}-\d{2}\.jsonl", n))
        con, lock = self.db._con, self.db._lock
        with lock:
            pos = dict(con.execute("SELECT name, pos FROM heard_spool").fetchall())
        total = 0
        now = datetime.now(timezone.utc)
        for name in names:
            path = SPOOL / name
            start = pos.get(name, 0)
            try:
                size = path.stat().st_size
                if size > start:
                    with open(path, "rb") as f:
                        f.seek(start)
                        chunk = f.read()
                    end = chunk.rfind(b"\n") + 1          # ligne en cours d'écriture : plus tard
                    lines = chunk[:end].decode("utf-8", errors="replace").splitlines()
                    touched = self._store(lines, home)
                    total += len(lines)
                    start += end
                    with lock:
                        con.execute("INSERT OR REPLACE INTO heard_spool (name, pos) VALUES (?, ?)", (name, start))
                        con.commit()
                    for d, h in touched:
                        self._summarize(d, h)
                hour_end = datetime.strptime(name[:11], "%Y%m%d-%H").replace(tzinfo=timezone.utc) + timedelta(hours=1)
                if now - hour_end > timedelta(minutes=10) and start >= path.stat().st_size:
                    path.unlink(missing_ok=True)       # heure terminée et entièrement lue
                    with lock:
                        con.execute("DELETE FROM heard_spool WHERE name = ?", (name,))
                        con.commit()
            except OSError as exc:
                log.info("journal autorun %s : %s", name, exc)
        if total:
            self.last_ingest = now.strftime("%Y-%m-%d %H:%M UTC")
            self.last_count = total
        return total

    def _store(self, lines, home):
        rows, touched = [], set()
        for line in lines:
            try:
                s = json.loads(line)
                t = int(s["t"])
                call = str(s["call"]).upper()[:16]
                band = str(s.get("band") or "")
            except (ValueError, KeyError, TypeError):
                continue
            if not call or not band:
                continue
            dt = datetime.fromtimestamp(t, timezone.utc)
            day, hour = dt.strftime("%Y%m%d"), dt.hour
            grid = str(s.get("grid") or "").upper()
            lat = lon = km = brg = None
            if geo.valid_locator(grid):
                lat, lon = geo.locator_to_latlon(grid)
                if home:
                    km, brg = geo.distance_bearing(home, (lat, lon))
            snr = s.get("snr")
            snr = int(round(snr)) if isinstance(snr, (int, float)) else None
            rows.append((day, hour, band, str(s.get("mode") or ""), call, grid, snr, t, t,
                         int(s.get("f") or 0) or None, lat, lon, km, brg))
            touched.add((day, hour))
        if rows:
            with self.db._lock:
                self.db._con.executemany(
                    "INSERT INTO heard (day, hour, band, mode, call, grid, snr, first_t, last_t, freq, lat, lon, km, bearing) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT (day, hour, band, mode, call) DO UPDATE SET "
                    "n = n + 1, last_t = max(last_t, excluded.last_t), snr = max(coalesce(snr, -99), coalesce(excluded.snr, -99)), "
                    "grid = CASE WHEN excluded.grid <> '' THEN excluded.grid ELSE grid END, "
                    "lat = coalesce(excluded.lat, lat), lon = coalesce(excluded.lon, lon), "
                    "km = coalesce(excluded.km, km), bearing = coalesce(excluded.bearing, bearing)", rows)
                self.db._con.commit()
        return touched

    def _summarize(self, day, hour):
        """Résumé permanent d'une heure, recalculé depuis le détail."""
        with self.db._lock:
            rows = self.db._con.execute(
                "SELECT band, call, km, bearing FROM heard WHERE day = ? AND hour = ?", (day, hour)).fetchall()
            agg = {}
            seen = set()
            for r in rows:
                key = (r["band"], sector_of(r["bearing"]))
                if (key, r["call"]) in seen:          # même station en FT8 et FT4 : une seule fois
                    continue
                seen.add((key, r["call"]))
                a = agg.setdefault(key, [0, None, None])
                a[0] += 1
                if r["km"] is not None and (a[1] is None or r["km"] > a[1]):
                    a[1], a[2] = r["km"], r["call"]
            self.db._con.execute("DELETE FROM heard_sum WHERE day = ? AND hour = ?", (day, hour))
            self.db._con.executemany(
                "INSERT INTO heard_sum (day, hour, band, sector, stations, max_km, max_call) VALUES (?,?,?,?,?,?,?)",
                [(day, hour, b, sec, a[0], a[1], a[2]) for (b, sec), a in agg.items()])
            self.db._con.commit()

    # ---------- FIFO ----------
    def prune(self):
        limit = (datetime.now(timezone.utc) - timedelta(days=HEARD_DAYS)).strftime("%Y%m%d")
        con = self.db._con
        with self.db._lock:
            con.execute("DELETE FROM heard WHERE day < ?", (limit,))
            n = con.execute("SELECT count(*) FROM heard").fetchone()[0]
            while n > HEARD_MAX_ROWS:
                oldest = con.execute("SELECT min(day) FROM heard").fetchone()[0]
                if not oldest:
                    break
                con.execute("DELETE FROM heard WHERE day = ?", (oldest,))
                n = con.execute("SELECT count(*) FROM heard").fetchone()[0]
            con.commit()

    # ---------- lecture ----------
    def day(self, day):
        """Page d'agenda : grille bande × heure, et stations les plus lointaines par bande."""
        with self.db._lock:
            grid = [dict(r) for r in self.db._con.execute(
                "SELECT band, hour, sum(stations) AS stations, max(max_km) AS max_km FROM heard_sum "
                "WHERE day = ? GROUP BY band, hour", (day,))]
            far = [dict(r) for r in self.db._con.execute(
                "SELECT band, call, grid, mode, max(km) AS km, bearing, snr, hour FROM heard "
                "WHERE day = ? AND km IS NOT NULL GROUP BY band, call ORDER BY km DESC", (day,))]
            detail = self.db._con.execute("SELECT count(*) FROM heard WHERE day = ?", (day,)).fetchone()[0]
        best = {}
        for f in far:
            best.setdefault(f["band"], [])
            if len(best[f["band"]]) < 5:
                best[f["band"]].append(f)
        return {"grid": grid, "farthest": best, "detail": bool(detail)}

    def around(self, qso_date, time_on, band, target_ll=None, bearing=None):
        """Fiche QSO : ce que le WebSDR décodait sur la bande, dans l'heure du QSO et les voisines."""
        if not band:
            return None
        t = (time_on or "0000").ljust(4, "0")
        when = datetime.strptime(qso_date + t[:4], "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
        keys = [((when + timedelta(hours=k)).strftime("%Y%m%d"), (when + timedelta(hours=k)).hour) for k in (-1, 0, 1)]
        with self.db._lock:
            rows = []
            for d, h in keys:
                rows += [dict(r) for r in self.db._con.execute(
                    "SELECT call, grid, mode, snr, lat, lon, km, bearing, hour, day FROM heard "
                    "WHERE day = ? AND hour = ? AND band = ?", (d, h, band))]
            summed = sum(r[0] or 0 for d, h in keys for r in self.db._con.execute(
                "SELECT sum(stations) FROM heard_sum WHERE day = ? AND hour = ? AND band = ?", (d, h, band)))
        if not rows and not summed:
            return None
        stations = {}
        for r in rows:
            s = stations.get(r["call"])
            if not s or (r["snr"] or -99) > (s["snr"] or -99):
                stations[r["call"]] = r
        st = list(stations.values())
        out = {"band": band, "stations": len(st) or summed, "detail": bool(st), "points": [], "toward": None, "near": None}
        located = [s for s in st if s["lat"] is not None]
        out["points"] = [{"call": s["call"], "lat": s["lat"], "lon": s["lon"], "snr": s["snr"], "km": s["km"]}
                         for s in sorted(located, key=lambda x: -(x["km"] or 0))[:300]]
        if bearing is not None:
            cone = [s for s in located if s["bearing"] is not None
                    and abs(((s["bearing"] - bearing + 180) % 360) - 180) <= 30]
            far = max(cone, key=lambda x: x["km"] or 0, default=None)
            out["toward"] = {"count": len(cone), "far_call": far["call"] if far else None,
                             "far_km": far["km"] if far else None, "far_snr": far["snr"] if far else None}
        if target_ll:
            near = min(located, key=lambda x: geo.distance_bearing(target_ll, (x["lat"], x["lon"]))[0], default=None)
            if near:
                d = geo.distance_bearing(target_ll, (near["lat"], near["lon"]))[0]
                out["near"] = {"call": near["call"], "km_from_target": d, "snr": near["snr"], "mode": near["mode"]}
        return out

    def status(self):
        with self.db._lock:
            n = self.db._con.execute("SELECT count(*) FROM heard").fetchone()[0]
            first = self.db._con.execute("SELECT min(day) FROM heard_sum").fetchone()[0]
        return {"spool": str(SPOOL), "spool_found": SPOOL.is_dir(), "rows": n, "since": first,
                "last_ingest": self.last_ingest, "last_count": self.last_count}
