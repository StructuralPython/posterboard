"""
The post as LinkedIn will show it, for the editor's live preview.

The text is converted exactly as it will be published. The HTML only adds what
LinkedIn draws itself: hashtags and URLs in its link colour, line breaks kept.
The collapsed view (three lines, then "…more") is done by the browser with a
line clamp at LinkedIn's feed width, so it wraps where LinkedIn would.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.utils.html import escape
from django.utils.safestring import SafeString, mark_safe

from .little_text import HASHTAG
from .unicode_text import to_unicode

# LinkedIn's limit for a post's text.
MAX_CHARS = 3000
URL = re.compile(r"https?://[^\s<>()]+[^\s<>().,;:!?'\"]")


@dataclass
class Preview:
    text: str
    html: SafeString
    chars: int

    @property
    def over_limit(self) -> bool:
        return self.chars > MAX_CHARS

    @property
    def max_chars(self) -> int:
        return MAX_CHARS


def _linkify(text: str) -> str:
    out, position = [], 0
    pattern = re.compile(f"{URL.pattern}|{HASHTAG.pattern}")
    for match in pattern.finditer(text):
        out.append(escape(text[position : match.start()]))
        out.append(f'<span class="li-link">{escape(match.group(0))}</span>')
        position = match.end()
    out.append(escape(text[position:]))
    return "".join(out)


def build(markdown: str) -> Preview:
    text = to_unicode(markdown)
    return Preview(text=text, html=mark_safe(_linkify(text)), chars=len(text))
