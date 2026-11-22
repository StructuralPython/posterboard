from __future__ import annotations

import secrets
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import linkedin, media
from .forms import PostForm
from .linkedin import LinkedInError
from .models import ImmutablePost, LinkedInConnection, Post
from .preview import build as build_preview

STATE_COOKIE = "posterboard_oauth_state"


# -- Dashboard -------------------------------------------------------------------


def dashboard(request):
    upcoming = Post.objects.filter(status__in=[
        Post.Status.SCHEDULED, Post.Status.PUBLISHING, Post.Status.FAILED,
    ]).order_by("publish_at")
    drafts = Post.objects.filter(status=Post.Status.DRAFT).order_by("-updated_at")
    previous = Post.objects.filter(status=Post.Status.PUBLISHED).order_by("-published_at")
    connection = LinkedInConnection.current()
    after_expiry = [
        p for p in upcoming
        if connection and p.publish_at and p.status == Post.Status.SCHEDULED
        and p.publish_at > connection.expires_at
    ]
    context = {
        "upcoming": upcoming,
        "drafts": drafts,
        "previous": previous,
        "after_expiry": after_expiry,
        # Refresh while something is about to be (or being) published.
        "refresh": any(
            p.status == Post.Status.PUBLISHING
            or (p.status == Post.Status.SCHEDULED and p.publish_at <= timezone.now() + timedelta(minutes=2))
            for p in upcoming
        ),
    }
    if request.headers.get("HX-Request"):
        return render(request, "posts/_lists.html", context)
    return render(request, "posts/dashboard.html", context)


# -- Editing -----------------------------------------------------------------------


def _store_upload(post: Post, upload, kind: str) -> None:
    _drop_media(post)
    post.media_kind = kind
    post.media.save(upload.name, upload, save=False)
    if kind == Post.Media.DOCUMENT:
        source = Path(settings.MEDIA_ROOT) / post.media.name
        pages_dir = source.with_suffix("").parent / f"{source.stem}-pages"
        post.media_pages, post.media_page_count = media.render_pages(source, pages_dir)


def _drop_media(post: Post) -> None:
    root = Path(settings.MEDIA_ROOT)
    if post.media:
        (root / post.media.name).unlink(missing_ok=True)
    for page in post.media_pages:
        (root / page).unlink(missing_ok=True)
    post.media = ""
    post.media_kind = ""
    post.media_pages = []
    post.media_page_count = 0


def edit(request, pk: int | None = None):
    post = get_object_or_404(Post, pk=pk) if pk else Post()
    if pk and not post.is_editable:
        messages.info(request, "Published posts can't be changed.")
        return redirect("post_detail", pk=post.pk)

    action = request.POST.get("action", "draft")
    form = PostForm(request.POST or None, request.FILES or None, instance=post, action=action)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                # The scheduler may have claimed the post since the page loaded.
                if pk and Post.objects.get(pk=pk).status not in Post.EDITABLE:
                    messages.error(request, "This post is being published and can no longer be edited.")
                    return redirect("dashboard")
                post = form.save(commit=False)
                if form.cleaned_data.get("remove_media"):
                    _drop_media(post)
                if form.cleaned_data.get("upload"):
                    _store_upload(post, form.cleaned_data["upload"], form.media_kind)
                post.error = ""
                if action == "now":
                    post.publish_at = timezone.now()
                    post.status = Post.Status.SCHEDULED
                elif action == "schedule":
                    post.status = Post.Status.SCHEDULED
                else:
                    post.status = Post.Status.DRAFT
                post.save()
        except ValidationError as exc:
            form.add_error("upload", exc)
        else:
            if action == "now":
                messages.success(request, "Posting now. It will be on LinkedIn within a minute.")
            elif action == "schedule":
                local = timezone.localtime(post.publish_at)
                messages.success(request, f"Scheduled for {local:%a %b %-d, %-I:%M %p}.")
                connection = LinkedInConnection.current()
                if connection and post.publish_at > connection.expires_at:
                    messages.warning(request, "That's after your LinkedIn connection expires: "
                                              "reconnect before then or it won't post.")
            else:
                messages.success(request, "Draft saved.")
            return redirect("dashboard")

    return render(request, "posts/edit.html", {
        "form": form,
        "post": post,
        "preview": build_preview(form["body"].value() or ""),
    })


def preview(request):
    """The live preview, re-rendered as the post is typed (htmx)."""
    post = None
    if request.POST.get("post"):
        post = Post.objects.filter(pk=request.POST["post"]).first()
    return render(request, "posts/_preview.html", {
        "preview": build_preview(request.POST.get("body", "")),
        "post": post,
    })


def detail(request, pk: int):
    post = get_object_or_404(Post, pk=pk)
    if post.is_editable:
        return redirect("post_edit", pk=post.pk)
    return render(request, "posts/detail.html", {"post": post, "preview": build_preview(post.body),
                                                 "text": post.text})


@require_POST
def delete(request, pk: int):
    post = get_object_or_404(Post, pk=pk)
    try:
        with transaction.atomic():
            post.delete()
    except ImmutablePost:
        messages.error(request, "Published posts can't be deleted.")
    else:
        messages.success(request, "Post deleted.")
    return redirect("dashboard")


@require_POST
def duplicate(request, pk: int):
    """Start a new draft from any post, including a published one."""
    source = get_object_or_404(Post, pk=pk)
    post = Post.objects.create(body=source.body, media_title=source.media_title)
    messages.success(request, "Copied into a new draft (without its media).")
    return redirect("post_edit", pk=post.pk)


# -- LinkedIn connection -------------------------------------------------------------


def linkedin_connect(request):
    if not (settings.LINKEDIN_CLIENT_ID and settings.LINKEDIN_CLIENT_SECRET):
        messages.error(request, "Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET first.")
        return redirect("dashboard")
    state = secrets.token_urlsafe(24)
    response = redirect(linkedin.authorization_url(state))
    response.set_signed_cookie(
        STATE_COOKIE, state, salt="linkedin", max_age=600, httponly=True,
        secure=request.is_secure(), samesite="Lax",
    )
    return response


def linkedin_callback(request):
    expected = request.get_signed_cookie(STATE_COOKIE, default=None, salt="linkedin", max_age=600)
    if not expected or request.GET.get("state") != expected:
        return HttpResponseBadRequest("The LinkedIn sign-in expired or didn't start here. Try again.")
    if "error" in request.GET:
        messages.error(request, f"LinkedIn said: {request.GET.get('error_description') or request.GET['error']}")
        return redirect("dashboard")
    try:
        token = linkedin.exchange_code(request.GET.get("code", ""))
        member = linkedin.userinfo(token.access_token)
    except LinkedInError as exc:
        messages.error(request, str(exc))
        return redirect("dashboard")
    now = timezone.now()
    connection = LinkedInConnection.current() or LinkedInConnection(pk=1)
    connection.person_urn = member.urn
    connection.name = member.name
    connection.picture_url = member.picture_url
    connection.access_token = token.access_token
    connection.scope = token.scope
    connection.connected_at = now
    connection.expires_at = now + timedelta(seconds=token.expires_in)
    connection.save()
    messages.success(request, f"Connected as {member.name}. Renew within {connection.days_left()} days.")
    response = redirect("dashboard")
    response.delete_cookie(STATE_COOKIE)
    return response


@require_POST
def linkedin_disconnect(request):
    LinkedInConnection.objects.filter(pk=1).delete()
    messages.success(request, "Disconnected from LinkedIn. Scheduled posts won't publish until you reconnect.")
    return redirect("dashboard")


def media_file(request, path: str):
    """Uploaded media (Caddy and tinyauth already guard every request)."""
    root = Path(settings.MEDIA_ROOT).resolve()
    target = (root / path).resolve()
    if root not in target.parents or not target.is_file():
        raise Http404
    from django.views.static import serve

    return serve(request, str(target.relative_to(root)), document_root=str(root))


def privacy(request):
    return render(request, "posts/privacy.html", {
        "contact_email": settings.POSTERBOARD_CONTACT_EMAIL,
        "site_url": settings.POSTERBOARD_URL,
    })


def healthz(request):
    return HttpResponse("ok")
