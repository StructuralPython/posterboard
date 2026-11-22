"""
Markdown to LinkedIn text.

LinkedIn posts are plain text, so emphasis is written with Unicode's
mathematical alphanumeric letters, which LinkedIn shows as styled text:

- ``**bold**`` -> 𝗯𝗼𝗹𝗱 (sans-serif bold; digits too)
- ``*italic*`` -> 𝘪𝘵𝘢𝘭𝘪𝘤 (sans-serif italic; Unicode has no italic digits)
- ``***both***`` -> 𝙗𝙤𝙩𝙝 (sans-serif bold italic)
- `` `code` `` -> 𝚌𝚘𝚍𝚎 (monospace; digits too)

Only ASCII letters and digits have styled forms. Everything else (accents,
punctuation, emoji) is left as written.

The Markdown is parsed with `wenmode <https://pypi.org/project/wenmode/>`_,
inline rules only. A line starting with ``-``, ``1.``, ``#`` or ``>`` stays as
written, so lists and hashtags are typed the way they will look. Blank lines
are kept exactly: wenmode joins paragraphs, so each paragraph is rendered on
its own. A link ``[label](url)`` becomes ``label (url)``; LinkedIn links the
URL itself.
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass

from wenmode import Wenmode
from wenmode.presets import Autolink, BackslashEscape, Emphasis, InlineCode, Link
from wenmode.renderers import BaseRenderer, RenderContext

__all__ = ["to_unicode", "STYLES", "style_text"]


def _alphabet(upper: int, lower: int, digits: int | None) -> dict[str, str]:
    """Map ASCII letters (and digits) to the Unicode block starting at the given code points."""
    table = {c: chr(upper + i) for i, c in enumerate(string.ascii_uppercase)}
    table.update({c: chr(lower + i) for i, c in enumerate(string.ascii_lowercase)})
    if digits is not None:
        table.update({c: chr(digits + i) for i, c in enumerate(string.digits)})
    return table


# Code points of A, a and 0 in each Mathematical Alphanumeric Symbols style.
STYLES: dict[str, dict[str, str]] = {
    "bold": _alphabet(0x1D5D4, 0x1D5EE, 0x1D7EC),
    "italic": _alphabet(0x1D608, 0x1D622, None),
    "bold_italic": _alphabet(0x1D63C, 0x1D656, 0x1D7EC),
    "mono": _alphabet(0x1D670, 0x1D68A, 0x1D7F6),
}


def style_text(text: str, style: str | None) -> str:
    if style is None:
        return text
    table = STYLES[style]
    return "".join(table.get(c, c) for c in text)


@dataclass(frozen=True)
class _Emphasis:
    bold: bool = False
    italic: bool = False

    @property
    def style(self) -> str | None:
        if self.bold and self.italic:
            return "bold_italic"
        if self.bold:
            return "bold"
        if self.italic:
            return "italic"
        return None


class UnicodeRenderer(BaseRenderer):
    """Renders inline Markdown nodes as plain text in Unicode styles."""

    def __init__(self) -> None:
        super().__init__()
        self.emphasis = _Emphasis()

    def styled(self, node, context: RenderContext, **change) -> str:
        outer = self.emphasis
        self.emphasis = _Emphasis(**{**outer.__dict__, **change})
        try:
            return self.render_children(node.children, context)
        finally:
            self.emphasis = outer


@UnicodeRenderer.register("text")
def _text(renderer: UnicodeRenderer, node, context: RenderContext) -> str:
    return style_text(node.value, renderer.emphasis.style)


@UnicodeRenderer.register("strong")
def _strong(renderer: UnicodeRenderer, node, context: RenderContext) -> str:
    return renderer.styled(node, context, bold=True)


@UnicodeRenderer.register("emphasis")
def _emphasis(renderer: UnicodeRenderer, node, context: RenderContext) -> str:
    return renderer.styled(node, context, italic=True)


@UnicodeRenderer.register("inlineCode")
def _code(renderer: UnicodeRenderer, node, context: RenderContext) -> str:
    # Unicode has no bold or italic monospace, so code is monospace inside emphasis too.
    return style_text(node.value, "mono")


@UnicodeRenderer.register("link")
def _link(renderer: UnicodeRenderer, node, context: RenderContext) -> str:
    label = renderer.render_children(node.children, context)
    plain = "".join(child.value for child in node.children if getattr(child, "value", None))
    if plain == node.url:  # an autolink, <https://...>
        return node.url
    return f"{label} ({node.url})"


INLINE_RULES = (BackslashEscape, Emphasis, InlineCode, Link, Autolink)
_wen = Wenmode(rules=INLINE_RULES, renderer=UnicodeRenderer())
# A blank line (possibly with spaces), kept as written between paragraphs.
_PARAGRAPH_BREAK = re.compile(r"(\n[ \t]*\n\s*)")


def to_unicode(markdown: str) -> str:
    """``markdown`` (bold, italic, code) as LinkedIn post text in Unicode styles."""
    markdown = markdown.replace("\r\n", "\n")
    parts = _PARAGRAPH_BREAK.split(markdown)
    out = []
    for i, part in enumerate(parts):
        if i % 2:  # a paragraph break
            out.append(part)
        elif part:
            # wenmode drops leading/trailing whitespace of a paragraph; keep it.
            lead = part[: len(part) - len(part.lstrip())]
            trail = part[len(part.rstrip()) :]
            out.append(lead + _wen.render(part.strip()) + trail)
    return "".join(out)
