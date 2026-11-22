"""Settings for the test suite: debug off, a fixed secret, LinkedIn credentials set."""

import os
import tempfile

os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret")
os.environ.setdefault("POSTERBOARD_DATA_DIR", tempfile.mkdtemp(prefix="posterboard-test-"))
os.environ.setdefault("LINKEDIN_CLIENT_ID", "client-id")
os.environ.setdefault("LINKEDIN_CLIENT_SECRET", "client-secret")
os.environ.setdefault("POSTERBOARD_URL", "https://posterboard.example.com")

from .settings import *  # noqa: E402,F403

ALLOWED_HOSTS = ["testserver", "posterboard.example.com"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
