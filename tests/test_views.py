import io
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
import responses
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from posts.linkedin import TOKEN_URL, USERINFO_URL
from posts.models import LinkedInConnection, Post

pytestmark = pytest.mark.django_db


def local(dt):
    return timezone.localtime(dt).strftime("%Y-%m-%dT%H:%M")


def test_requests_without_the_tinyauth_header_are_refused():
    assert Client().get("/").status_code == 403


def test_a_spoofed_header_is_stripped_by_caddy_not_django():
    # Django trusts the header; deploy/Caddyfile removes any client copy first.
    assert "request_header -Remote-User" in open("deploy/Caddyfile").read()


def test_dashboard_lists_scheduled_drafts_and_previous(client, connection):
    Post.objects.create(body="Upcoming one", status="scheduled", publish_at=timezone.now() + timedelta(days=1))
    Post.objects.create(body="A draft")
    Post.objects.create(body="Old one", status="published", published_at=timezone.now(),
                        published_text="Old one", linkedin_urn="urn:li:share:1")
    html = client.get("/").content.decode()
    for text in ("Upcoming one", "A draft", "Old one", "49 days left", "View on LinkedIn"):
        assert text in html


def test_dashboard_without_connection_offers_to_connect(client):
    assert "Connect LinkedIn" in client.get("/").content.decode()


def test_save_a_draft(client):
    response = client.post("/posts/new/", {"body": "**Draft**", "action": "draft"})
    assert response.status_code == 302
    post = Post.objects.get()
    assert post.status == "draft" and post.publish_at is None


def test_schedule_a_post(client, connection):
    when = timezone.now() + timedelta(days=2)
    client.post("/posts/new/", {"body": "Soon", "action": "schedule", "publish_at": local(when)})
    post = Post.objects.get()
    assert post.status == "scheduled"
    assert abs((post.publish_at - when).total_seconds()) < 60


def test_scheduling_in_the_past_is_refused(client):
    response = client.post("/posts/new/", {"body": "Late", "action": "schedule",
                                           "publish_at": local(timezone.now() - timedelta(hours=1))})
    assert response.status_code == 200
    assert "That time has passed" in response.content.decode()
    assert not Post.objects.exists()


def test_scheduling_after_the_token_expires_warns(client, connection):
    when = connection.expires_at + timedelta(days=3)
    response = client.post("/posts/new/", {"body": "Far", "action": "schedule", "publish_at": local(when)},
                           follow=True)
    assert "after your LinkedIn connection expires" in response.content.decode()


def test_post_now_schedules_it_for_now(client):
    client.post("/posts/new/", {"body": "Now!", "action": "now"})
    post = Post.objects.get()
    assert post.status == "scheduled" and post.publish_at <= timezone.now()


def test_an_empty_post_cannot_be_scheduled(client):
    response = client.post("/posts/new/", {"body": "  ", "action": "now"})
    assert "Write something first" in response.content.decode()


def test_text_over_the_limit_is_refused(client):
    response = client.post("/posts/new/", {"body": "x" * 3001, "action": "draft"})
    assert "at most 3000" in response.content.decode()


def test_edit_a_scheduled_post(client):
    post = Post.objects.create(body="Old", status="scheduled", publish_at=timezone.now() + timedelta(days=1))
    client.post(f"/posts/{post.pk}/edit/", {"body": "New", "action": "schedule",
                                            "publish_at": local(post.publish_at)})
    post.refresh_from_db()
    assert post.body == "New"


def test_published_posts_open_read_only(client):
    post = Post.objects.create(body="Done", status="published", published_text="Done",
                               published_at=timezone.now(), linkedin_urn="urn:li:share:1")
    response = client.get(f"/posts/{post.pk}/edit/")
    assert response.status_code == 302 and response.url == f"/posts/{post.pk}/"
    response = client.post(f"/posts/{post.pk}/delete/", follow=True)
    assert "Published posts can&#x27;t be deleted." in response.content.decode()
    assert Post.objects.filter(pk=post.pk).exists()
    assert "Edit or delete them on LinkedIn" in client.get(f"/posts/{post.pk}/").content.decode()


def test_a_post_claimed_by_the_scheduler_cannot_be_saved(client):
    post = Post.objects.create(body="Racing", status="scheduled", publish_at=timezone.now())
    Post.objects.filter(pk=post.pk).update(status="publishing")
    # The edit page was loaded before the claim; the save arrives after it.
    response = client.post(f"/posts/{post.pk}/edit/", {"body": "Changed", "action": "draft"}, follow=True)
    post.refresh_from_db()
    assert post.body == "Racing"


def test_copy_a_published_post_into_a_draft(client):
    post = Post.objects.create(body="Original", status="published", published_text="Original",
                               published_at=timezone.now())
    response = client.post(f"/posts/{post.pk}/duplicate/")
    copy = Post.objects.exclude(pk=post.pk).get()
    assert copy.body == "Original" and copy.status == "draft"
    assert response.url == f"/posts/{copy.pk}/edit/"


def test_live_preview(client):
    response = client.post("/preview/", {"body": "**Bold** #tag"})
    html = response.content.decode()
    assert "𝗕𝗼𝗹𝗱" in html and '<span class="li-link">#tag</span>' in html
    assert "/ 3000 characters" in html


def test_image_upload(client, media_root):
    buffer = io.BytesIO()
    Image.new("RGB", (40, 20), "teal").save(buffer, "PNG")
    upload = SimpleUploadedFile("beam.png", buffer.getvalue(), content_type="image/png")
    client.post("/posts/new/", {"body": "Pic", "action": "draft", "upload": upload})
    post = Post.objects.get()
    assert post.media_kind == "image" and (media_root / post.media.name).exists()
    assert client.get(reverse("media", args=[post.media.name])).status_code == 200


def test_pdf_upload_renders_carousel_pages(client, media_root):
    buffer = io.BytesIO()
    pages = [Image.new("RGB", (400, 400), c) for c in ("navy", "teal", "white")]
    pages[0].save(buffer, "PDF", save_all=True, append_images=pages[1:])
    upload = SimpleUploadedFile("tour.pdf", buffer.getvalue(), content_type="application/pdf")
    client.post("/posts/new/", {"body": "Slides", "action": "draft", "upload": upload, "media_title": "Tour"})
    post = Post.objects.get()
    assert post.media_kind == "document" and post.media_page_count == 3
    assert all((media_root / p).exists() for p in post.media_pages)
    html = client.get(f"/posts/{post.pk}/edit/").content.decode()
    assert "Tour · 3 pages" in html


def test_unsupported_files_are_refused(client):
    upload = SimpleUploadedFile("notes.docx", b"x")
    response = client.post("/posts/new/", {"body": "Doc", "action": "draft", "upload": upload})
    assert "LinkedIn accepts" in response.content.decode()


def test_media_paths_cannot_escape_the_media_folder(client):
    assert client.get("/media/../config/settings.py").status_code == 404


def test_delete_removes_the_media(client, media_root):
    post = Post.objects.create(body="x", media_kind="image")
    from django.core.files.base import ContentFile

    post.media.save("a.png", ContentFile(b"1"))
    path = media_root / post.media.name
    client.post(f"/posts/{post.pk}/delete/")
    assert not path.exists() and not Post.objects.exists()


# -- LinkedIn sign-in ---------------------------------------------------------------


def start_connect(client):
    response = client.get("/linkedin/connect/")
    assert response.status_code == 302
    query = parse_qs(urlparse(response.url).query)
    assert query["scope"] == ["openid profile w_member_social"]
    assert query["redirect_uri"] == ["https://posterboard.example.com/linkedin/callback/"]
    return query["state"][0]


@responses.activate
def test_connect_stores_the_token_and_its_expiry(client):
    state = start_connect(client)
    responses.add(responses.POST, TOKEN_URL, json={
        "access_token": "new-token", "expires_in": 5184000, "scope": "openid,profile,w_member_social"})
    responses.add(responses.GET, USERINFO_URL, json={"sub": "xyz", "name": "Connor F", "picture": ""})
    response = client.get("/linkedin/callback/", {"code": "c0de", "state": state}, follow=True)
    connection = LinkedInConnection.current()
    assert connection.person_urn == "urn:li:person:xyz"
    assert connection.access_token == "new-token"
    assert connection.days_left() == 59
    assert "Connected as Connor F" in response.content.decode()
    assert "code=c0de" in responses.calls[0].request.body


def test_callback_with_the_wrong_state_is_refused(client):
    start_connect(client)
    assert client.get("/linkedin/callback/", {"code": "c", "state": "forged"}).status_code == 400


def test_callback_reports_a_denied_sign_in(client):
    state = start_connect(client)
    response = client.get("/linkedin/callback/", {"error": "user_cancelled_login",
                                                  "error_description": "The member declined", "state": state},
                          follow=True)
    assert "The member declined" in response.content.decode()
    assert LinkedInConnection.current() is None


def test_disconnect(client, connection):
    client.post("/linkedin/disconnect/")
    assert LinkedInConnection.current() is None
