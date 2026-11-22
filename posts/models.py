from __future__ import annotations

import math
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import models
from django.utils import timezone

from . import crypto


class LinkedInConnection(models.Model):
    """
    The LinkedIn account Posterboard posts as: there is at most one (pk=1).

    LinkedIn gives self-serve apps a 60-day access token and no refresh token,
    so the token is renewed by signing in to LinkedIn again before it expires.
    """

    person_urn = models.CharField(max_length=100)
    name = models.CharField(max_length=200, blank=True)
    picture_url = models.URLField(max_length=1000, blank=True)
    access_token_encrypted = models.TextField()
    scope = models.CharField(max_length=500, blank=True)
    connected_at = models.DateTimeField()
    expires_at = models.DateTimeField()

    @classmethod
    def current(cls) -> LinkedInConnection | None:
        return cls.objects.filter(pk=1).first()

    @property
    def access_token(self) -> str:
        return crypto.decrypt(self.access_token_encrypted)

    @access_token.setter
    def access_token(self, value: str) -> None:
        self.access_token_encrypted = crypto.encrypt(value)

    def time_left(self, now=None) -> timedelta:
        return self.expires_at - (now or timezone.now())

    def days_left(self, now=None) -> int:
        """Whole days until the token expires (0 on its last day, negative once expired)."""
        return math.floor(self.time_left(now).total_seconds() / 86400)

    def is_expired(self, now=None) -> bool:
        return self.time_left(now) <= timedelta(0)

    def needs_renewal(self, now=None) -> bool:
        return self.days_left(now) < settings.LINKEDIN_RENEW_WARNING_DAYS

    @property
    def lifetime_days(self) -> int:
        return max(1, round((self.expires_at - self.connected_at).total_seconds() / 86400))

    def __str__(self) -> str:
        return self.name or self.person_urn


class ImmutablePost(Exception):
    """A published post cannot be changed or deleted."""


def upload_to(post: Post, filename: str) -> str:
    return f"uploads/{timezone.now():%Y/%m}/{Path(filename).name}"


class Post(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled"
        PUBLISHING = "publishing", "Publishing"
        PUBLISHED = "published", "Published"
        FAILED = "failed", "Failed"

    class Media(models.TextChoices):
        NONE = "", "No media"
        IMAGE = "image", "Image"
        VIDEO = "video", "Video"
        DOCUMENT = "document", "Carousel (PDF)"

    EDITABLE = {Status.DRAFT, Status.SCHEDULED, Status.FAILED}

    body = models.TextField(help_text="Markdown: **bold**, *italic*, `code`.")
    media_kind = models.CharField(max_length=10, choices=Media.choices, blank=True, default="")
    media = models.FileField(upload_to=upload_to, blank=True)
    # A carousel's title, or an image's or video's alt text.
    media_title = models.CharField(max_length=400, blank=True)
    # Rendered pages of a carousel PDF (paths under MEDIA_ROOT), for the preview.
    media_pages = models.JSONField(default=list, blank=True)
    media_page_count = models.PositiveIntegerField(default=0)

    publish_at = models.DateTimeField(null=True, blank=True, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)

    # Filled when the post is published, and never changed afterwards.
    published_at = models.DateTimeField(null=True, blank=True)
    published_text = models.TextField(blank=True)
    linkedin_urn = models.CharField(max_length=200, blank=True)
    error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["publish_at", "created_at"]

    def __str__(self) -> str:
        first = self.body.strip().splitlines()[0] if self.body.strip() else "(empty)"
        return first[:60]

    @property
    def is_editable(self) -> bool:
        return self.status in self.EDITABLE

    @property
    def linkedin_url(self) -> str:
        return f"https://www.linkedin.com/feed/update/{self.linkedin_urn}/" if self.linkedin_urn else ""

    @property
    def text(self) -> str:
        """The post as it reads on LinkedIn: the published text, or the draft converted."""
        if self.published_text:
            return self.published_text
        from .unicode_text import to_unicode

        return to_unicode(self.body)

    def _stored_status(self) -> str | None:
        if self.pk is None:
            return None
        return Post.objects.filter(pk=self.pk).values_list("status", flat=True).first()

    def save(self, *args, **kwargs):
        if self._stored_status() == self.Status.PUBLISHED:
            raise ImmutablePost(f"Post {self.pk} is published and cannot change.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self._stored_status() in (self.Status.PUBLISHED, self.Status.PUBLISHING):
            raise ImmutablePost(f"Post {self.pk} is {self.status} and cannot be deleted.")
        for path in [self.media.name, *self.media_pages] if self.media else self.media_pages:
            (Path(settings.MEDIA_ROOT) / path).unlink(missing_ok=True)
        return super().delete(*args, **kwargs)
