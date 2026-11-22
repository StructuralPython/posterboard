import json
from datetime import timedelta

import pytest
import responses
from django.core.files.base import ContentFile
from django.utils import timezone

from posts import publishing
from posts.linkedin import REST
from posts.models import Post

POST_URN = "urn:li:share:7000"


def scheduled(body="Hello **world** (now) #python", minutes_ago=1, **kwargs):
    return Post.objects.create(
        body=body, status=Post.Status.SCHEDULED,
        publish_at=timezone.now() - timedelta(minutes=minutes_ago), **kwargs,
    )


def add_post_endpoint(rsps):
    rsps.add(responses.POST, f"{REST}/posts", status=201, headers={"x-restli-id": POST_URN})


@responses.activate
def test_a_due_text_post_is_published(connection):
    add_post_endpoint(responses)
    post = scheduled()
    future = scheduled(minutes_ago=-60)
    done = publishing.publish_due()
    assert [p.pk for p in done] == [post.pk]
    post.refresh_from_db()
    assert post.status == Post.Status.PUBLISHED
    assert post.linkedin_urn == POST_URN
    assert post.published_text == "Hello 𝘄𝗼𝗿𝗹𝗱 (now) #python"
    assert post.linkedin_url == f"https://www.linkedin.com/feed/update/{POST_URN}/"
    request = responses.calls[0].request
    assert request.headers["Authorization"] == "Bearer token-xyz"
    assert request.headers["LinkedIn-Version"]
    assert request.headers["X-Restli-Protocol-Version"] == "2.0.0"
    body = json.loads(request.body)
    assert body["author"] == "urn:li:person:abc123"
    assert body["commentary"] == r"Hello 𝘄𝗼𝗿𝗹𝗱 \(now\) {hashtag|\#|python}"
    assert body["lifecycleState"] == "PUBLISHED" and "content" not in body
    future.refresh_from_db()
    assert future.status == Post.Status.SCHEDULED


@responses.activate
def test_an_image_is_uploaded_then_attached(connection):
    responses.add(responses.POST, f"{REST}/images", json={"value": {
        "uploadUrl": "https://upload.example/img", "image": "urn:li:image:42"}})
    responses.add(responses.PUT, "https://upload.example/img", status=201)
    add_post_endpoint(responses)
    post = scheduled(media_kind=Post.Media.IMAGE, media_title="A beam")
    post.media.save("beam.png", ContentFile(b"png-bytes"))
    publishing.publish_due()
    post.refresh_from_db()
    assert post.status == Post.Status.PUBLISHED, post.error
    assert responses.calls[1].request.body == b"png-bytes"
    body = json.loads(responses.calls[2].request.body)
    assert body["content"] == {"media": {"id": "urn:li:image:42", "altText": "A beam"}}


@responses.activate
def test_a_carousel_pdf_is_a_document_with_a_title(connection):
    responses.add(responses.POST, f"{REST}/documents", json={"value": {
        "uploadUrl": "https://upload.example/doc", "document": "urn:li:document:9"}})
    responses.add(responses.PUT, "https://upload.example/doc", status=201)
    add_post_endpoint(responses)
    post = scheduled(media_kind=Post.Media.DOCUMENT)
    post.media.save("ymprint-tour.pdf", ContentFile(b"%PDF-1.4"))
    publishing.publish_due()
    body = json.loads(responses.calls[2].request.body)
    # Without a title, the file name is used: LinkedIn requires one for documents.
    assert body["content"] == {"media": {"id": "urn:li:document:9", "title": "ymprint-tour"}}


@responses.activate
def test_a_video_is_uploaded_in_parts_and_waited_for(connection, monkeypatch):
    data = b"0123456789"
    responses.add(responses.POST, f"{REST}/videos", json={"value": {
        "video": "urn:li:video:5", "uploadToken": "tok",
        "uploadInstructions": [
            {"uploadUrl": "https://upload.example/v1", "firstByte": 0, "lastByte": 5},
            {"uploadUrl": "https://upload.example/v2", "firstByte": 6, "lastByte": 9},
        ]}})
    responses.add(responses.PUT, "https://upload.example/v1", headers={"etag": '"e1"'})
    responses.add(responses.PUT, "https://upload.example/v2", headers={"etag": '"e2"'})
    responses.add(responses.POST, f"{REST}/videos", status=200)  # finalize
    responses.add(responses.GET, f"{REST}/videos/urn%3Ali%3Avideo%3A5", json={"status": "PROCESSING"})
    responses.add(responses.GET, f"{REST}/videos/urn%3Ali%3Avideo%3A5", json={"status": "AVAILABLE"})
    add_post_endpoint(responses)
    monkeypatch.setattr("posts.linkedin.time.sleep", lambda s: None)
    post = scheduled(media_kind=Post.Media.VIDEO)
    post.media.save("demo.mp4", ContentFile(data))
    publishing.publish_due()
    post.refresh_from_db()
    assert post.status == Post.Status.PUBLISHED, post.error
    assert responses.calls[1].request.body == b"012345"
    assert responses.calls[2].request.body == b"6789"
    finalize = json.loads(responses.calls[3].request.body)["finalizeUploadRequest"]
    assert finalize == {"video": "urn:li:video:5", "uploadToken": "tok", "uploadedPartIds": ["e1", "e2"]}


@responses.activate
def test_a_linkedin_error_fails_the_post_with_the_reason(connection):
    responses.add(responses.POST, f"{REST}/posts", status=422, json={"message": "Duplicate post"})
    post = scheduled()
    publishing.publish_due()
    post.refresh_from_db()
    assert post.status == Post.Status.FAILED
    assert "Duplicate post" in post.error and "422" in post.error
    assert post.is_editable


@responses.activate
def test_an_expired_token_is_explained(connection):
    responses.add(responses.POST, f"{REST}/posts", status=401, json={"message": "Invalid access token"})
    post = scheduled()
    publishing.publish_due()
    post.refresh_from_db()
    assert "reconnect" in post.error


@pytest.mark.django_db
def test_no_connection_fails_without_calling_linkedin():
    post = scheduled()
    publishing.publish_due()
    post.refresh_from_db()
    assert post.status == Post.Status.FAILED and "not connected" in post.error


def test_a_connection_expired_before_the_post_fails(connection):
    connection.expires_at = timezone.now() - timedelta(hours=1)
    connection.save()
    post = scheduled()
    publishing.publish_due()
    post.refresh_from_db()
    assert "expired" in post.error


@pytest.mark.django_db
def test_a_claimed_post_is_never_published_twice():
    post = scheduled()
    assert publishing.claim(post)
    assert not publishing.claim(Post.objects.get(pk=post.pk))


@pytest.mark.django_db
def test_an_interrupted_publish_is_failed_not_retried():
    post = scheduled()
    Post.objects.filter(pk=post.pk).update(
        status=Post.Status.PUBLISHING, updated_at=timezone.now() - timedelta(hours=1)
    )
    assert publishing.fail_stale() == 1
    post.refresh_from_db()
    assert post.status == Post.Status.FAILED and "may already be there" in post.error
