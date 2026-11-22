from posts.little_text import hashtags, to_little_text
from posts.preview import build
from posts.unicode_text import to_unicode


def test_bold_italic_and_code():
    assert to_unicode("**Bold 12** and *italic* and ***both*** and `x_1`") == (
        "𝗕𝗼𝗹𝗱 𝟭𝟮 and 𝘪𝘵𝘢𝘭𝘪𝘤 and 𝙗𝙤𝙩𝙝 and 𝚡_𝟷"
    )


def test_unstyled_characters_are_kept():
    # Accents, punctuation and emoji have no styled forms.
    assert to_unicode("**café, 100%!** 🚀") == "𝗰𝗮𝗳é, 𝟭𝟬𝟬%! 🚀"


def test_italic_digits_stay_plain():
    assert to_unicode("*v2*") == "𝘷2"


def test_code_inside_bold_is_monospace():
    assert to_unicode("**run `ym` now**") == "𝗿𝘂𝗻 𝚢𝚖 𝗻𝗼𝘄"


def test_blank_lines_and_line_breaks_are_kept():
    text = "First line\nsecond line\n\n\nNew paragraph\n"
    assert to_unicode(text) == text


def test_lists_and_hashtags_stay_as_written():
    text = "- one\n- two\n1. three\n# not a heading\n> not a quote\n#python"
    assert to_unicode(text) == text


def test_links():
    assert to_unicode("see [the docs](https://ymprint.com) or <https://a.b/c>") == (
        "see the docs (https://ymprint.com) or https://a.b/c"
    )


def test_backslash_escapes():
    assert to_unicode(r"2\*3\*4 and \*not italic\*") == "2*3*4 and *not italic*"


def test_little_text_escapes_reserved_characters():
    assert to_little_text("a (b) [c] {d} <e> @f *g* _h_ ~i~ |j| \\k") == (
        r"a \(b\) \[c\] \{d\} \<e\> \@f \*g\* \_h\_ \~i\~ \|j\| \\k"
    )


def test_little_text_links_hashtags():
    assert to_little_text("New release #python #StructuralEngineering!") == (
        r"New release {hashtag|\#|python} {hashtag|\#|StructuralEngineering}!"
    )
    assert hashtags("a #b c#d #e_f") == ["b", "e_f"]


def test_a_hash_inside_a_word_is_escaped_not_a_hashtag():
    assert to_little_text("C# and issue#12") == r"C\# and issue\#12"


def test_preview_highlights_links_and_hashtags_and_counts():
    preview = build("**Hi** see https://ymprint.com #python <b>")
    assert '<span class="li-link">https://ymprint.com</span>' in preview.html
    assert '<span class="li-link">#python</span>' in preview.html
    assert "&lt;b&gt;" in preview.html  # escaped
    assert preview.chars == len("𝗛𝗶 see https://ymprint.com #python <b>")
    assert not preview.over_limit
    assert build("x" * 3001).over_limit
