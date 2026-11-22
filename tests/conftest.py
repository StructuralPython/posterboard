from datetime import timedelta

import pytest
from django.utils import timezone

from posts.models import LinkedInConnection


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.MEDIA_ROOT.mkdir()
    return settings.MEDIA_ROOT


@pytest.fixture
def client(client):
    """A test client signed in the way Caddy and tinyauth sign requests in."""
    client.defaults["HTTP_REMOTE_USER"] = "connor"
    return client


@pytest.fixture
def connection(db):
    now = timezone.now()
    conn = LinkedInConnection(
        pk=1, person_urn="urn:li:person:abc123", name="Connor Ferster",
        connected_at=now - timedelta(days=10), expires_at=now + timedelta(days=50),
    )
    conn.access_token = "token-xyz"
    conn.save()
    return conn
