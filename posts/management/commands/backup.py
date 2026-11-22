"""Back up the database and media with rclone: ``manage.py backup [--every 300]``."""

import logging
import signal
import time

from django.core.management.base import BaseCommand

from posts.backup import backup_once

log = logging.getLogger("posts.backup")


class Command(BaseCommand):
    help = "Back up the SQLite database and media to POSTERBOARD_BACKUP_REMOTE."

    def add_arguments(self, parser):
        parser.add_argument("--every", type=int, default=0,
                            help="Repeat every N seconds (0: once). The container uses 300.")

    def handle(self, *args, every=0, **options):
        stopping = False

        def stop(*_):
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGTERM, stop)
        while True:
            try:
                backup_once()
            except Exception:
                log.exception("Backup failed; retrying next time")
            if not every or stopping:
                break
            for _ in range(every):
                if stopping:
                    break
                time.sleep(1)
        if every:
            # One last backup on shutdown, so recent edits aren't lost.
            try:
                backup_once()
            except Exception:
                log.exception("Final backup failed")
