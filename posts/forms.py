from __future__ import annotations

from django import forms
from django.utils import timezone

from . import media
from .models import Post
from .preview import MAX_CHARS
from .unicode_text import to_unicode

ACTIONS = ("draft", "schedule", "now")


class PostForm(forms.ModelForm):
    upload = forms.FileField(
        required=False, label="Media",
        help_text="An image (JPG, PNG, GIF), a video (MP4) or a carousel (PDF).",
        widget=forms.ClearableFileInput(attrs={"accept": ".jpg,.jpeg,.png,.gif,.mp4,.pdf"}),
    )
    remove_media = forms.BooleanField(required=False, label="Remove media")
    publish_at = forms.DateTimeField(
        required=False, label="Post at",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        input_formats=["%Y-%m-%dT%H:%M"],
    )

    class Meta:
        model = Post
        fields = ["body", "media_title", "publish_at"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 16, "spellcheck": "true"}),
            "media_title": forms.TextInput(),
        }
        labels = {"body": "Post", "media_title": "Carousel title or alt text"}

    def __init__(self, *args, action: str = "draft", **kwargs):
        super().__init__(*args, **kwargs)
        self.action = action if action in ACTIONS else "draft"
        self.media_kind = None

    def clean_upload(self):
        upload = self.cleaned_data.get("upload")
        if upload:
            self.media_kind = media.validate(upload)
        return upload

    def clean_body(self):
        body = self.cleaned_data["body"]
        if len(to_unicode(body)) > MAX_CHARS:
            raise forms.ValidationError(f"LinkedIn posts can have at most {MAX_CHARS} characters.")
        return body

    def clean(self):
        data = super().clean()
        if self.action == "schedule":
            when = data.get("publish_at")
            if not when:
                self.add_error("publish_at", "Choose when to post it.")
            elif when <= timezone.now():
                self.add_error("publish_at", "That time has passed. Choose a later one, or post it now.")
        if self.action in ("schedule", "now") and not (data.get("body") or "").strip():
            self.add_error("body", "Write something first.")
        return data
