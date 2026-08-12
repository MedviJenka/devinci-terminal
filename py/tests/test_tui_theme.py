"""The oh-my-pi gradient engine — color sampling and text construction."""

from __future__ import annotations

from tui.theme import BRAND_STOPS, OH_MY_PI, gradient_text, hex_of


def test_hex_of_formats_palette_rgb() -> None:
    assert hex_of(OH_MY_PI["cyan"]) == "#4adeff"


def test_gradient_text_keeps_the_original_characters() -> None:
    text = gradient_text("DeVinci")
    assert text.plain == "DeVinci"


def test_gradient_text_colors_each_visible_char() -> None:
    text = gradient_text("abc", stops=BRAND_STOPS)
    # Every non-space char carries its own interpolated style span.
    assert len(text.spans) == 3


def test_gradient_text_leaves_spaces_uncolored() -> None:
    text = gradient_text("a b")
    # Two visible chars styled; the space is appended without a span.
    assert len(text.spans) == 2
    assert text.plain == "a b"
