"""
The oh-my-pi aesthetic — neon palette + gradient text, ported to Rich/Textual.

The palette and per-character linear-interpolation gradient mirror the original
`OH_MY_PI` / `gradient()` from index.js, so the Python TUI keeps the same
cyan → violet → pink → lime → amber look. `gradient_text` accepts an animation
`phase` in [0, 1) that rotates where the gradient samples, which the app steps on
a timer to make the banner shimmer.
"""

from rich.color import Color
from rich.style import Style
from rich.text import Text


__all__ = ["OH_MY_PI", "BRAND_STOPS", "gradient_text", "hex_of"]


# RGB triples, identical to the OH_MY_PI palette in index.js.
OH_MY_PI: dict[str, tuple[int, int, int]] = {
    "cyan": (74, 222, 255),
    "violet": (168, 85, 247),
    "pink": (236, 72, 153),
    "lime": (163, 230, 53),
    "amber": (251, 191, 36),
    "red": (248, 113, 113),
    "slate": (148, 163, 184),
}

# The default multi-stop gradient the brand banner flows through.
BRAND_STOPS: tuple[tuple[int, int, int], ...] = (
    OH_MY_PI["cyan"],
    OH_MY_PI["violet"],
    OH_MY_PI["pink"],
    OH_MY_PI["amber"],
    OH_MY_PI["cyan"],
)


def hex_of(rgb: tuple[int, int, int]) -> str:
    """'#4adeff'-style hex for a palette RGB triple (for Textual CSS)."""
    r, g, b = rgb
    return f"#{r:02x}{g:02x}{b:02x}"


def _sample(stops: tuple[tuple[int, int, int], ...], t: float) -> tuple[int, int, int]:
    """Sample a multi-stop gradient at position t in [0, 1] (linear per channel)."""
    if len(stops) == 1:
        return stops[0]
    t = t - int(t)  # wrap into [0, 1)
    scaled = t * (len(stops) - 1)
    left = int(scaled)
    if left >= len(stops) - 1:
        return stops[-1]
    frac = scaled - left
    a, b = stops[left], stops[left + 1]
    return tuple(round(a[c] + (b[c] - a[c]) * frac) for c in range(3))  # type: ignore[return-value]


def gradient_text(text: str, stops: tuple = BRAND_STOPS, *, phase: float = 0.0, bold: bool = False) -> Text:
    """Return a Rich Text whose characters flow through `stops`.

    `phase` shifts the sampling window (animate it for a moving shimmer); spaces
    are left uncolored, matching the original gradient() behaviour.
    """
    chars = list(text)
    span = max(1, len(chars) - 1)
    out = Text()

    for index, char in enumerate(chars):
        if char == " ":
            out.append(" ")
            continue
        t = (index / span) + phase
        r, g, b = _sample(stops, t)
        out.append(char, Style(color=Color.from_rgb(r, g, b), bold=bold))

    return out
