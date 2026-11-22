"""
Post text in LinkedIn's "little text" format.

The ``commentary`` of a post is little text: some characters are markup, and an
unescaped one can cut a post short or drop part of it. Every reserved character
is escaped with a backslash, except hashtags (``#word``), which become
LinkedIn's hashtag template so they stay clickable.

https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/little-text-format
"""

from __future__ import annotations

import re

RESERVED = set("|{}@[]()<>#\\*_~")

# A hashtag starts a word: '#' then letters, digits or underscores (any script).
HASHTAG = re.compile(r"(?<![\w#])#(\w+)")


def escape(text: str) -> str:
    return "".join(f"\\{c}" if c in RESERVED else c for c in text)


def to_little_text(text: str) -> str:
    """``text`` (already in Unicode styles) as little text, hashtags linked."""
    out, position = [], 0
    for match in HASHTAG.finditer(text):
        out.append(escape(text[position : match.start()]))
        out.append(f"{{hashtag|\\#|{escape(match.group(1))}}}")
        position = match.end()
    out.append(escape(text[position:]))
    return "".join(out)


def hashtags(text: str) -> list[str]:
    return HASHTAG.findall(text)
