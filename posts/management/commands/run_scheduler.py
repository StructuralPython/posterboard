"""Publish scheduled posts when they are due: ``manage.py run_scheduler``."""

import logging
import signal
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from posts.publishing import publish_due

log = logging.getLogger("posts.scheduler")


class Command(BaseCommand):
    help = "Publish scheduled posts as they come due (runs until stopped)."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Run one pass and exit.")
        parser.add_argument("--interval", type=int, default=settings.SCHEDULER_INTERVAL)

    def handle(self, *args, once=False, interval=30, **options):
        stopping = False

        def stop(*_):
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        log.info("Scheduler started (every %ss).", interval)
        while not stopping:
            close_old_connections()
            try:
                for post in publish_due():
                    log.info("Post %s: %s", post.pk, post.status)
            except Exception:  # keep the loop alive; the next pass retries
                log.exception("Scheduler pass failed")
            if once:
                break
            for _ in range(interval):
                if stopping:
                    break
                time.sleep(1)
        log.info("Scheduler stopped.")
