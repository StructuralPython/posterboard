"""
Posterboard's own scheduler: publishes posts whose time has come.

LinkedIn can schedule posts, but Posterboard doesn't use that: it keeps the
schedule itself and publishes through the immediate-post API when a post is due.

A post is claimed by switching it from ``scheduled`` to ``publishing`` in one
UPDATE, so two scheduler passes can never publish it twice. A post found still
``publishing`` long after it started (the container restarted mid-publish) is
marked failed rather than retried: it may already be on LinkedIn, so a person
checks before posting it again.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from .linkedin import LinkedInClient, LinkedInError
from .little_text import to_little_text
from .models import LinkedInConnection, Post
from .unicode_text import to_unicode

log = logging.getLogger(__name__)

STALE_AFTER = timedelta(minutes=30)


def due_posts(now=None):
    now = now or timezone.now()
    return Post.objects.filter(status=Post.Status.SCHEDULED, publish_at__lte=now).order_by("publish_at")


def claim(post: Post) -> bool:
    """Move ``post`` from scheduled to publishing; False if something else got there first."""
    claimed = Post.objects.filter(pk=post.pk, status=Post.Status.SCHEDULED).update(
        status=Post.Status.PUBLISHING, updated_at=timezone.now()
    )
    if claimed:
        post.status = Post.Status.PUBLISHING
    return bool(claimed)


def client_for(connection: LinkedInConnection) -> LinkedInClient:
    return LinkedInClient(connection.access_token, connection.person_urn)


def publish(post: Post, client: LinkedInClient) -> None:
    """Upload the post's media and publish it now. ``post`` must be claimed."""
    text = to_unicode(post.body)
    media_urn = None
    if post.media and post.media_kind:
        path = Path(settings.MEDIA_ROOT) / post.media.name
        upload = {
            Post.Media.IMAGE: client.upload_image,
            Post.Media.VIDEO: client.upload_video,
            Post.Media.DOCUMENT: client.upload_document,
        }[post.media_kind]
        media_urn = upload(path)
    is_document = post.media_kind == Post.Media.DOCUMENT
    urn = client.create_post(
        to_little_text(text),
        media_urn,
        title=(post.media_title or Path(post.media.name).stem) if is_document else "",
        alt_text="" if is_document else post.media_title,
    )
    post.linkedin_urn = urn
    post.published_text = text
    post.published_at = timezone.now()
    post.error = ""
    post.status = Post.Status.PUBLISHED
    post.save()


def fail(post: Post, message: str) -> None:
    post.status = Post.Status.FAILED
    post.error = message
    post.save()


def publish_due(now=None, client: LinkedInClient | None = None) -> list[Post]:
    """Publish every due post; returns them (published or failed)."""
    now = now or timezone.now()
    fail_stale(now)
    posts = [post for post in due_posts(now) if claim(post)]
    if not posts:
        return []
    connection = LinkedInConnection.current()
    for post in posts:
        if client is None:
            if connection is None:
                fail(post, "LinkedIn is not connected. Connect it, then reschedule this post.")
                continue
            if connection.is_expired(now):
                fail(post, "The LinkedIn connection expired before this post was due. "
                           "Reconnect, then reschedule it.")
                continue
        try:
            publish(post, client or client_for(connection))
            log.info("Published post %s as %s", post.pk, post.linkedin_urn)
        except LinkedInError as exc:
            log.warning("Post %s failed: %s", post.pk, exc)
            fail(post, str(exc))
        except Exception as exc:  # never leave a post stuck in 'publishing'
            log.exception("Post %s failed", post.pk)
            fail(post, f"Unexpected error: {exc}")
    return posts


def fail_stale(now=None) -> int:
    now = now or timezone.now()
    stale = Post.objects.filter(status=Post.Status.PUBLISHING, updated_at__lt=now - STALE_AFTER)
    count = 0
    for post in stale:
        fail(post, "Publishing was interrupted. Check LinkedIn before rescheduling: "
                   "the post may already be there.")
        count += 1
    return count
