"""
Backups of the SQLite database and uploaded media to bunny.net storage, with rclone.

Every pass takes a consistent snapshot with SQLite's online backup API (safe
while the app writes), and uploads it only if it changed since the last upload.
Media files are copied (never deleted remotely). Once a day the snapshot is also
kept under ``daily/`` so a bad change can be rolled back.

Remote layout under ``POSTERBOARD_BACKUP_REMOTE`` (e.g. ``bunny:posterboard``):

    posterboard.sqlite3
    daily/2026-11-22.sqlite3
    media/uploads/...
"""

from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import subprocess
from datetime import date
from pathlib import Path

from django.conf import settings

log = logging.getLogger("posts.backup")

DB_NAME = "posterboard.sqlite3"


def remote() -> str:
    return os.environ.get("POSTERBOARD_BACKUP_REMOTE", "").rstrip("/")


def rclone(*args: str) -> None:
    command = ["rclone", *args]
    log.debug("%s", " ".join(command))
    subprocess.run(command, check=True, capture_output=True, text=True)


def snapshot(db_path: Path, target: Path) -> Path:
    """A consistent copy of the live database."""
    target.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(db_path)
    try:
        copy = sqlite3.connect(target)
        try:
            source.backup(copy)
        finally:
            copy.close()
    finally:
        source.close()
    return target


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def backup_once(state_dir: Path | None = None) -> bool:
    """Upload the database (if it changed) and new media. Returns True if the database was uploaded."""
    dest = remote()
    if not dest:
        log.warning("POSTERBOARD_BACKUP_REMOTE is not set; skipping backup.")
        return False
    db_path = Path(settings.DATABASES["default"]["NAME"])
    state_dir = state_dir or Path(settings.DATA_DIR) / ".backup"
    snap = snapshot(db_path, state_dir / DB_NAME)
    digest = _digest(snap)
    marker = state_dir / "last-upload.sha256"
    uploaded = False
    if not marker.exists() or marker.read_text().strip() != digest:
        rclone("copyto", str(snap), f"{dest}/{DB_NAME}")
        marker.write_text(digest)
        uploaded = True
        log.info("Database backed up.")
    daily_marker = state_dir / "last-daily"
    today = date.today().isoformat()
    if not daily_marker.exists() or daily_marker.read_text().strip() != today:
        rclone("copyto", str(snap), f"{dest}/daily/{today}.sqlite3")
        daily_marker.write_text(today)
    media = Path(settings.MEDIA_ROOT)
    if media.exists() and any(media.iterdir()):
        rclone("copy", str(media), f"{dest}/media")
    return uploaded


def restore_if_missing() -> bool:
    """On a fresh container, fetch the database and media from the backup. True if restored."""
    dest = remote()
    db_path = Path(settings.DATABASES["default"]["NAME"])
    if not dest or db_path.exists():
        return False
    db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        rclone("copyto", f"{dest}/{DB_NAME}", str(db_path))
    except subprocess.CalledProcessError as exc:
        if "not found" in (exc.stderr or "").lower() or "directory not found" in (exc.stderr or "").lower():
            log.info("No backup yet; starting with a new database.")
            return False
        raise
    rclone("copy", f"{dest}/media", str(settings.MEDIA_ROOT))
    log.info("Restored the database and media from %s.", dest)
    return True
