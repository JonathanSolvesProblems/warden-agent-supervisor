"""Generate the Devpost 1280x720 cover image for Warden.

Run from the repo root:

    python -m scripts.generate_cover

Writes preview/cover.png. Reproducible and font-bundled (fonts live in
preview/.fonts so this script needs no system font install).
"""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "preview" / ".fonts"
OUT = ROOT / "preview" / "cover.png"

W, H = 1280, 720
BG = (11, 15, 23)
ACCENT = (91, 140, 255)
GOLD = (244, 194, 94)
TEXT = (230, 237, 246)
DIM = (130, 149, 173)


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        FONT_DIR / name,
        Path("C:/Windows/Fonts") / name.replace("JetBrainsMono-Bold", "consolab").replace("JetBrainsMono-Medium", "consolab").replace("JetBrainsMono-Regular", "consola"),
    ]
    for p in candidates:
        if p.exists():
            return ImageFont.truetype(str(p), size)
    raise FileNotFoundError(f"missing font {name}, ran from {os.getcwd()}")


def _segoe(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    p = Path("C:/Windows/Fonts") / ("segoeuib.ttf" if bold else "segoeui.ttf")
    return ImageFont.truetype(str(p), size)


def _radial_gradient(size, center, inner_color, outer_color, radius):
    cx, cy = center
    layer = Image.new("RGB", size, outer_color)
    px = layer.load()
    r2 = radius * radius
    for y in range(size[1]):
        for x in range(size[0]):
            dx = x - cx
            dy = y - cy
            d2 = dx * dx + dy * dy
            if d2 >= r2:
                continue
            t = (d2 / r2) ** 0.5
            r = int(inner_color[0] * (1 - t) + outer_color[0] * t)
            g = int(inner_color[1] * (1 - t) + outer_color[1] * t)
            b = int(inner_color[2] * (1 - t) + outer_color[2] * t)
            px[x, y] = (r, g, b)
    return layer


def _draw_brandmark(draw: ImageDraw.ImageDraw, x: int, y: int, size: int):
    """Two bracket strokes + center dot, in cyan accent.

    Modeled on the dashboard SVG:
        M5 5 L5 27 L10 27
        M27 5 L27 27 L22 27
        circle cx 16 cy 16 r 3
    Scaled from 32x32 to size x size.
    """
    s = size / 32
    stroke = max(3, int(3 * s))

    def p(px, py):
        return (x + px * s, y + py * s)

    draw.line([p(5, 5), p(5, 27), p(10, 27)], fill=ACCENT, width=stroke, joint="curve")
    draw.line([p(27, 5), p(27, 27), p(22, 27)], fill=ACCENT, width=stroke, joint="curve")
    r = 3 * s
    cx, cy = p(16, 16)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ACCENT)


def _text_with_tracking(draw, xy, text, font, fill, tracking_px=0):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        bbox = font.getbbox(ch)
        x += (bbox[2] - bbox[0]) + tracking_px


def build() -> Path:
    img = _radial_gradient(
        (W, H),
        center=(int(W * 0.85), int(H * 0.18)),
        inner_color=(22, 36, 59),
        outer_color=BG,
        radius=900,
    )
    img = img.filter(ImageFilter.GaussianBlur(radius=1.5))

    # very faint horizontal scan line at the divider position is created via the
    # divider rectangle below, not a separate texture, to keep the image clean.
    draw = ImageDraw.Draw(img, "RGBA")

    # brandmark + wordmark, baseline at y=300
    mark_x, mark_y = 150, 240
    _draw_brandmark(draw, mark_x, mark_y, size=96)

    wordmark_font = _font("JetBrainsMono-Bold.ttf", 152)
    wordmark_x = mark_x + 96 + 56
    wordmark_y = mark_y - 12
    _text_with_tracking(
        draw,
        (wordmark_x, wordmark_y),
        "WARDEN",
        wordmark_font,
        TEXT,
        tracking_px=8,
    )

    # tagline
    tagline = "the agent that governs your agents"
    tagline_font = _segoe(30, bold=False)
    draw.text((wordmark_x + 4, wordmark_y + 158), tagline, font=tagline_font, fill=DIM)

    # divider line, 1 px tall, cyan accent at ~25% opacity, from 12% to 88%
    div_y = 460
    draw.line(
        [(int(W * 0.12), div_y), (int(W * 0.88), div_y)],
        fill=(*ACCENT, 64),
        width=1,
    )

    # three section labels under the divider
    section_font = _font("JetBrainsMono-Medium.ttf", 22)
    sub_font = _font("JetBrainsMono-Regular.ttf", 20)

    sections = [
        ("01 / SENSE", "Dynatrace MCP", ACCENT),
        ("02 / REASON", "Gemini 3", GOLD),
        ("03 / GOVERN", "human-gated action", TEXT),
    ]
    col_x = [160, 575, 945]
    label_y = 510
    sub_y = 545

    for (label, sub, sub_color), x in zip(sections, col_x):
        draw.text((x, label_y), label, font=section_font, fill=DIM)
        draw.text((x, sub_y), sub, font=sub_font, fill=sub_color)

    # bottom-right metadata
    meta_font = _font("JetBrainsMono-Regular.ttf", 16)
    meta_lines = [
        ("Dynatrace track", DIM),
        ("Google Cloud Rapid Agent Hackathon", DIM),
    ]
    meta_x_right = W - 56
    meta_y = H - 90
    for i, (line, color) in enumerate(meta_lines):
        bbox = meta_font.getbbox(line)
        w = bbox[2] - bbox[0]
        draw.text((meta_x_right - w, meta_y + i * 26), line, font=meta_font, fill=color)

    # top-left status pill
    pill_font = _font("JetBrainsMono-Medium.ttf", 14)
    pill_text = "AGENT-RELIABILITY SUPERVISOR"
    bbox = pill_font.getbbox(pill_text)
    pad_x, pad_y = 14, 7
    px0, py0 = 150, 150
    px1 = px0 + (bbox[2] - bbox[0]) + 2 * pad_x
    py1 = py0 + (bbox[3] - bbox[1]) + 2 * pad_y
    draw.rounded_rectangle(
        [px0, py0, px1, py1],
        radius=4,
        outline=(*DIM, 120),
        width=1,
    )
    draw.text((px0 + pad_x, py0 + pad_y - 2), pill_text, font=pill_font, fill=DIM)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, "PNG", optimize=True)
    return OUT


if __name__ == "__main__":
    out = build()
    print(f"wrote {out}  ({out.stat().st_size / 1024:.1f} KB)")
