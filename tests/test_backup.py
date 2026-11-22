import sqlite3
import subprocess

import pytest

from posts import backup
from posts.models import Post

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def calls(monkeypatch, settings, tmp_path):
    db = tmp_path / "live.sqlite3"
    con = sqlite3.connect(db)
    con.execute("create table t (x)")
    con.execute("insert into t values (1)")
    con.commit()
    con.close()
    monkeypatch.setitem(settings.DATABASES["default"], "NAME", db)
    monkeypatch.setenv("POSTERBOARD_BACKUP_REMOTE", "bunny:pb")
    recorded = []
    monkeypatch.setattr(backup, "rclone", lambda *args: recorded.append(args))
    return recorded


def test_snapshot_is_a_working_copy(tmp_path):
    src = tmp_path / "a.sqlite3"
    con = sqlite3.connect(src)
    con.execute("create table t (x)")
    con.execute("insert into t values (42)")
    con.commit()
    copy = backup.snapshot(src, tmp_path / "out" / "b.sqlite3")
    assert sqlite3.connect(copy).execute("select x from t").fetchone() == (42,)


def test_backup_uploads_only_when_changed(calls, tmp_path, settings):
    state = tmp_path / "state"
    assert backup.backup_once(state)
    db_uploads = [c for c in calls if c[-1] == "bunny:pb/posterboard.sqlite3"]
    daily = [c for c in calls if "/daily/" in c[-1]]
    assert len(db_uploads) == 1 and len(daily) == 1
    calls.clear()
    assert not backup.backup_once(state)  # unchanged: nothing uploaded
    assert calls == []


def test_media_is_copied_never_synced(calls, tmp_path, media_root):
    (media_root / "uploads").mkdir()
    (media_root / "uploads" / "a.png").write_bytes(b"1")
    backup.backup_once(tmp_path / "state")
    assert ("copy", str(media_root), "bunny:pb/media") in calls


def test_no_remote_means_no_backup(calls, monkeypatch, tmp_path):
    monkeypatch.delenv("POSTERBOARD_BACKUP_REMOTE")
    assert not backup.backup_once(tmp_path / "state")
    assert calls == []


def test_restore_only_when_the_database_is_missing(calls, settings, tmp_path, monkeypatch):
    assert not backup.restore_if_missing()  # the database exists
    monkeypatch.setitem(settings.DATABASES["default"], "NAME", tmp_path / "fresh" / "db.sqlite3")
    assert backup.restore_if_missing()
    assert calls[0] == ("copyto", "bunny:pb/posterboard.sqlite3", str(tmp_path / "fresh" / "db.sqlite3"))


def test_restore_with_no_backup_yet_starts_fresh(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("POSTERBOARD_BACKUP_REMOTE", "bunny:pb")
    monkeypatch.setitem(settings.DATABASES["default"], "NAME", tmp_path / "db.sqlite3")

    def missing(*args):
        raise subprocess.CalledProcessError(3, args, stderr="ERROR : error reading source root directory: directory not found")

    monkeypatch.setattr(backup, "rclone", missing)
    assert not backup.restore_if_missing()


def test_an_empty_database_file_counts_as_missing(calls, settings, tmp_path, monkeypatch):
    # Opening a connection (e.g. Django's start-up checks) creates an empty file.
    empty = tmp_path / "empty.sqlite3"
    empty.touch()
    monkeypatch.setitem(settings.DATABASES["default"], "NAME", empty)
    assert backup.restore_if_missing()


def test_restore_without_media_in_the_backup(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("POSTERBOARD_BACKUP_REMOTE", "bunny:pb")
    monkeypatch.setitem(settings.DATABASES["default"], "NAME", tmp_path / "db.sqlite3")

    def rclone(*args):
        if args[-1] == str(settings.MEDIA_ROOT):
            raise subprocess.CalledProcessError(3, args, stderr="directory not found")

    monkeypatch.setattr(backup, "rclone", rclone)
    assert backup.restore_if_missing()
