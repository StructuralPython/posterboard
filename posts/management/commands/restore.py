"""Fetch the database and media from the backup when the database is missing."""

from django.core.management.base import BaseCommand

from posts.backup import restore_if_missing


class Command(BaseCommand):
    # System checks open the database, which would create an empty one first.
    requires_system_checks = []
    help = "Restore the database and media from POSTERBOARD_BACKUP_REMOTE if there is no database yet."

    def handle(self, *args, **options):
        if restore_if_missing():
            self.stdout.write("Restored from backup.")
        else:
            self.stdout.write("Nothing to restore.")
