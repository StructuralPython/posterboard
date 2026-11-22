"""Checks uploads against LinkedIn's limits, and renders carousel pages for the preview."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

MB = 1024 * 1024

# Per LinkedIn's Images, Videos and Documents API docs.
KINDS = {
    "image": {"extensions": {".jpg", ".jpeg", ".png", ".gif"}, "max_bytes": 36 * MB},
    "video": {"extensions": {".mp4"}, "max_bytes": 500 * MB},
    "document": {"extensions": {".pdf"}, "max_bytes": 100 * MB, "max_pages": 300},
}
PREVIEW_WIDTH = 540  # pixels, about LinkedIn's feed width


def kind_for(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    for kind, rules in KINDS.items():
        if suffix in rules["extensions"]:
            return kind
    allowed = ", ".join(sorted(e for r in KINDS.values() for e in r["extensions"]))
    raise ValidationError(f"LinkedIn accepts {allowed} files.")


def validate(upload) -> str:
    kind = kind_for(upload.name)
    limit = KINDS[kind]["max_bytes"]
    if upload.size > limit:
        raise ValidationError(f"That {kind} is {upload.size / MB:.0f} MB; LinkedIn's limit is {limit // MB} MB.")
    return kind


def render_pages(pdf_path: Path, out_dir: Path, max_pages: int = 300) -> tuple[list[str], int]:
    """
    Render each page of a PDF to a JPEG for the carousel preview. Returns the
    image paths (relative to MEDIA_ROOT) and the page count.
    """
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        count = len(pdf)
        if count > max_pages:
            raise ValidationError(f"That PDF has {count} pages; LinkedIn's limit is {max_pages}.")
        out_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for index in range(count):
            page = pdf[index]
            scale = PREVIEW_WIDTH / page.get_width()
            image = page.render(scale=scale).to_pil()
            target = out_dir / f"page-{index + 1:03d}.jpg"
            image.convert("RGB").save(target, quality=82)
            paths.append(str(target.relative_to(settings.MEDIA_ROOT)))
        return paths, count
    finally:
        pdf.close()
