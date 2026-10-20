"""Sauvegardes de la base : une copie automatique par jour, gardée 30 jours, dans data/backups/.

Chaque copie est un fichier SQLite complet (orsatlog-AAAAMMJJ.db), utilisable tel quel
par le bouton « Restaurer » des Réglages ou par n'importe quel lecteur SQLite.
"""

import asyncio
import logging
import re
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .db import DATA_DIR

log = logging.getLogger("orsatlog.backup")

BACKUP_DIR = DATA_DIR / "backups"
KEEP_DAYS = 30
_NAME = re.compile(r"^orsatlog-\d{8}(-\d{4})?\.db$")


def valid_name(name):
    return bool(_NAME.match(name or ""))


def list_backups():
    if not BACKUP_DIR.is_dir():
        return []
    out = []
    for p in sorted(BACKUP_DIR.glob("orsatlog-*.db"), reverse=True):
        if valid_name(p.name):
            st = p.stat()
            out.append({"name": p.name, "size": st.st_size,
                        "time": datetime.fromtimestamp(st.st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")})
    return out


def make_backup(db, name=None):
    """Écrit une copie dans data/backups/ et renvoie son chemin."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    name = name or f"orsatlog-{datetime.now(timezone.utc):%Y%m%d}.db"
    path = BACKUP_DIR / name
    tmp = path.with_suffix(".tmp")
    db.backup_to(tmp)
    tmp.replace(path)
    return path


def prune():
    """Ne garde que les KEEP_DAYS copies quotidiennes les plus récentes (les copies
    d'avant restauration, horodatées à la minute, sont gardées aussi longtemps)."""
    items = sorted(BACKUP_DIR.glob("orsatlog-*.db"), reverse=True)
    for p in items[KEEP_DAYS:]:
        p.unlink(missing_ok=True)


def snapshot_file(db):
    """Copie fraîche dans un fichier temporaire, pour le téléchargement."""
    fd, tmp = tempfile.mkstemp(suffix=".db", dir=DATA_DIR)
    Path(tmp).unlink()
    db.backup_to(tmp)
    return Path(tmp)


def check_logbook_file(path):
    """Vrai si le fichier est une base ORSAT-LOG (SQLite intègre, avec la table qso)."""
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                return False
            return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='qso'").fetchone() is not None
        finally:
            con.close()
    except sqlite3.Error:
        return False


async def daily_task(db):
    """Copie du jour au démarrage si elle manque, puis vérification toutes les heures."""
    while True:
        try:
            today = BACKUP_DIR / f"orsatlog-{datetime.now(timezone.utc):%Y%m%d}.db"
            if not today.exists():
                await asyncio.to_thread(make_backup, db)
                await asyncio.to_thread(prune)
                log.info("Sauvegarde quotidienne : %s", today.name)
        except Exception as exc:
            log.warning("Sauvegarde quotidienne impossible : %s", exc)
        await asyncio.sleep(3600)
