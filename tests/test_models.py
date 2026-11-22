from datetime import timedelta

import pytest
from django.utils import timezone

from posts.models import ImmutablePost, LinkedInConnection, Post


def test_token_is_encrypted_at_rest(connection):
    raw = LinkedInConnection.objects.values_list("access_token_encrypted", flat=True).get()
    assert "token-xyz" not in raw
    assert LinkedInConnection.current().access_token == "token-xyz"


def test_days_left_and_renewal(connection, settings):
    now = timezone.now()
    assert connection.days_left(now) == 49  # 50 days minus a moment
    assert not connection.needs_renewal(now)
    assert connection.needs_renewal(now + timedelta(days=40))
    assert connection.days_left(connection.expires_at + timedelta(hours=1)) == -1
    assert connection.is_expired(connection.expires_at)
    assert connection.lifetime_days == 60


@pytest.mark.django_db
def test_published_posts_cannot_change_or_be_deleted():
    post = Post.objects.create(body="hi", status=Post.Status.PUBLISHED, linkedin_urn="urn:li:share:1")
    post.body = "changed"
    with pytest.raises(ImmutablePost):
        post.save()
    with pytest.raises(ImmutablePost):
        post.delete()
    assert Post.objects.get().body == "hi"


@pytest.mark.django_db
def test_scheduled_and_failed_posts_can_change():
    post = Post.objects.create(body="hi", status=Post.Status.FAILED)
    post.body = "changed"
    post.save()
    post.delete()
    assert not Post.objects.exists()
