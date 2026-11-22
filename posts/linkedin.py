"""
LinkedIn API: OpenID Connect sign-in and posting to the member's profile.

Everything here works with a self-serve app that has the "Share on LinkedIn" and
"Sign In with LinkedIn using OpenID Connect" products (scopes ``openid profile
w_member_social``). Posts go through the versioned ``/rest/posts`` API; media is
uploaded first through the Images, Videos or Documents API and attached by URN.

Docs:
- https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow
- https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2
- https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api
- .../shares/images-api, .../shares/videos-api, .../shares/documents-api
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

import requests
from django.conf import settings

log = logging.getLogger(__name__)

AUTHORIZE_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
REST = "https://api.linkedin.com/rest"

TIMEOUT = 60
UPLOAD_TIMEOUT = 600


class LinkedInError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _raise_for(response: requests.Response, what: str) -> None:
    if response.ok:
        return
    try:
        detail = response.json().get("message") or response.text
    except ValueError:
        detail = response.text
    if response.status_code == 401:
        detail = f"{detail} (the LinkedIn connection has expired or was revoked: reconnect)"
    raise LinkedInError(f"{what} failed ({response.status_code}): {detail[:500]}", response.status_code)


# -- OAuth ---------------------------------------------------------------------


def authorization_url(state: str) -> str:
    query = {
        "response_type": "code",
        "client_id": settings.LINKEDIN_CLIENT_ID,
        "redirect_uri": settings.LINKEDIN_REDIRECT_URI,
        "state": state,
        "scope": settings.LINKEDIN_SCOPES,
    }
    return f"{AUTHORIZE_URL}?{urlencode(query)}"


@dataclass
class Token:
    access_token: str
    expires_in: int  # seconds
    scope: str


def exchange_code(code: str) -> Token:
    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.LINKEDIN_REDIRECT_URI,
            "client_id": settings.LINKEDIN_CLIENT_ID,
            "client_secret": settings.LINKEDIN_CLIENT_SECRET,
        },
        timeout=TIMEOUT,
    )
    _raise_for(response, "Getting a LinkedIn token")
    data = response.json()
    return Token(data["access_token"], int(data["expires_in"]), data.get("scope", ""))


@dataclass
class Member:
    urn: str
    name: str
    picture_url: str


def userinfo(access_token: str) -> Member:
    response = requests.get(
        USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=TIMEOUT
    )
    _raise_for(response, "Reading your LinkedIn profile")
    data = response.json()
    return Member(f"urn:li:person:{data['sub']}", data.get("name", ""), data.get("picture", ""))


# -- Posting -----------------------------------------------------------------------


class LinkedInClient:
    """Posts to one member's profile with their access token."""

    def __init__(self, access_token: str, author_urn: str, version: str | None = None,
                 session: requests.Session | None = None):
        self.author = author_urn
        self.session = session or requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {access_token}",
            "LinkedIn-Version": version or settings.LINKEDIN_API_VERSION,
            "X-Restli-Protocol-Version": "2.0.0",
        })
        # Seconds to wait between checks while LinkedIn processes a video.
        self.poll_interval = 5.0
        self.video_timeout = 600.0

    # Media ----------------------------------------------------------------

    def _initialize(self, kind: str, extra: dict | None = None) -> dict:
        response = self.session.post(
            f"{REST}/{kind}",
            params={"action": "initializeUpload"},
            json={"initializeUploadRequest": {"owner": self.author, **(extra or {})}},
            timeout=TIMEOUT,
        )
        _raise_for(response, f"Starting the {kind[:-1]} upload")
        return response.json()["value"]

    def _put(self, url: str, data: bytes, what: str) -> requests.Response:
        response = self.session.put(
            url, data=data, headers={"Content-Type": "application/octet-stream"},
            timeout=UPLOAD_TIMEOUT,
        )
        _raise_for(response, what)
        return response

    def upload_image(self, path: Path) -> str:
        value = self._initialize("images")
        self._put(value["uploadUrl"], Path(path).read_bytes(), "Uploading the image")
        return value["image"]

    def upload_document(self, path: Path) -> str:
        value = self._initialize("documents")
        self._put(value["uploadUrl"], Path(path).read_bytes(), "Uploading the PDF")
        return value["document"]

    def upload_video(self, path: Path) -> str:
        path = Path(path)
        size = path.stat().st_size
        value = self._initialize(
            "videos", {"fileSizeBytes": size, "uploadCaptions": False, "uploadThumbnail": False}
        )
        video = value["video"]
        etags = []
        with path.open("rb") as f:
            # LinkedIn splits large videos into parts (4 MB each) with their byte ranges.
            for part in value["uploadInstructions"]:
                f.seek(part["firstByte"])
                chunk = f.read(part["lastByte"] - part["firstByte"] + 1)
                response = self._put(part["uploadUrl"], chunk, "Uploading the video")
                etags.append(response.headers.get("etag", "").strip('"'))
        response = self.session.post(
            f"{REST}/videos",
            params={"action": "finalizeUpload"},
            json={"finalizeUploadRequest": {
                "video": video, "uploadToken": value.get("uploadToken", ""), "uploadedPartIds": etags,
            }},
            timeout=TIMEOUT,
        )
        _raise_for(response, "Finishing the video upload")
        self.wait_for_video(video)
        return video

    def wait_for_video(self, video: str) -> None:
        """Wait until LinkedIn has processed the video (posting earlier can fail)."""
        deadline = time.monotonic() + self.video_timeout
        while True:
            response = self.session.get(f"{REST}/videos/{requests.utils.quote(video, safe='')}",
                                        timeout=TIMEOUT)
            _raise_for(response, "Checking the video")
            status = response.json().get("status")
            if status == "AVAILABLE":
                return
            if status == "PROCESSING_FAILED":
                raise LinkedInError("LinkedIn could not process the video.")
            if time.monotonic() > deadline:
                raise LinkedInError("LinkedIn took too long to process the video.")
            time.sleep(self.poll_interval)

    # Posts ------------------------------------------------------------------

    def create_post(self, commentary: str, media_urn: str | None = None, title: str = "",
                    alt_text: str = "") -> str:
        """Publish a post now; returns its URN (``urn:li:share:...`` or ``urn:li:ugcPost:...``)."""
        body = {
            "author": self.author,
            "commentary": commentary,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        if media_urn:
            media = {"id": media_urn}
            if title:
                media["title"] = title
            if alt_text:
                media["altText"] = alt_text
            body["content"] = {"media": media}
        response = self.session.post(f"{REST}/posts", json=body, timeout=TIMEOUT)
        _raise_for(response, "Publishing the post")
        urn = response.headers.get("x-restli-id") or response.headers.get("x-linkedin-id")
        if not urn:
            raise LinkedInError("LinkedIn accepted the post but returned no post ID.")
        return urn
