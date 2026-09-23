"""Generate Pixie's icon: a sparkle, because she does the magic bit for you.

Run this only if you want to change the icon; the result is committed.

    python make_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

import theme

OUT = Path(__file__).resolve().parent / "pixie.ico"
SIZES = (256, 128, 64, 48, 32, 16)
RENDER_AT = 1024  # draw big, downscale smooth


def sparkle(draw: ImageDraw.ImageDraw, cx: float, cy: float, radius: float,
            waist: float, fill: tuple[int, int, int, int]) -> None:
    """A four-pointed star with concave sides."""
    draw.polygon(
        [
            (cx, cy - radius), (cx + waist, cy - waist), (cx + radius, cy),
            (cx + waist, cy + waist), (cx, cy + radius), (cx - waist, cy + waist),
            (cx - radius, cy), (cx - waist, cy - waist),
        ],
        fill=fill,
    )


def main() -> int:
    size = RENDER_AT
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Rounded dark tile, so the sparkle has something to sit on at small sizes.
    pad = size * 0.04
    draw.rounded_rectangle([pad, pad, size - pad, size - pad],
                           radius=size * 0.22, fill=(*_rgb(theme.PANEL), 255))

    accent = (*_rgb(theme.ACCENT), 255)
    glow = (*_rgb(theme.ACCENT), 70)

    # Soft glow behind the main sparkle.
    sparkle(draw, size * 0.46, size * 0.46, size * 0.44, size * 0.17, glow)
    # Main sparkle.
    sparkle(draw, size * 0.46, size * 0.46, size * 0.36, size * 0.085, accent)
    # Two small companions.
    sparkle(draw, size * 0.765, size * 0.25, size * 0.14, size * 0.032, accent)
    sparkle(draw, size * 0.73, size * 0.745, size * 0.10, size * 0.024,
            (*_rgb(theme.FG), 235))

    image.save(OUT, sizes=[(s, s) for s in SIZES])
    print(f"Wrote {OUT.name} at sizes {', '.join(str(s) for s in SIZES)}")
    return 0


def _rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


if __name__ == "__main__":
    raise SystemExit(main())
