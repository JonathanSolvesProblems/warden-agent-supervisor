"""Generate the architecture diagram for Warden.

Run from the repo root:

    python -m scripts.generate_architecture

Writes preview/architecture.png. Reproducible and font-bundled (fonts live in
preview/.fonts so this script needs no system font install).

Layout: five vertical layers, each a rounded panel with a section number, a
title row, and a content block. Cyan accent, warm-gold for the Gemini brain
to match the dashboard's color story.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "preview" / ".fonts"
OUT = ROOT / "preview" / "architecture.png"

W, H = 1400, 1900
PAD_X = 90
BG = (11, 15, 23)
PANEL = (24, 33, 47)
PANEL_2 = (19, 26, 38)
LINE = (36, 48, 66)
ACCENT = (91, 140, 255)
GOLD = (244, 194, 94)
GOOD = (46, 204, 143)
BAD = (255, 92, 99)
TEXT = (230, 237, 246)
DIM = (130, 149, 173)


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), size)


def _segoe(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    p = Path("C:/Windows/Fonts") / ("segoeuib.ttf" if bold else "segoeui.ttf")
    return ImageFont.truetype(str(p), size)


def _radial_gradient(size, center, inner_color, outer_color, radius):
    cx, cy = center
    img = Image.new("RGB", size, outer_color)
    px = img.load()
    r2 = radius * radius
    for y in range(size[1]):
        for x in range(size[0]):
            d2 = (x - cx) ** 2 + (y - cy) ** 2
            if d2 >= r2:
                continue
            t = (d2 / r2) ** 0.5
            r = int(inner_color[0] * (1 - t) + outer_color[0] * t)
            g = int(inner_color[1] * (1 - t) + outer_color[1] * t)
            b = int(inner_color[2] * (1 - t) + outer_color[2] * t)
            px[x, y] = (r, g, b)
    return img


def _panel(draw, x0, y0, x1, y1, fill=PANEL, outline=LINE):
    draw.rounded_rectangle([x0, y0, x1, y1], radius=20, fill=fill, outline=outline, width=2)


def _arrow(draw, x, y0, y1, color=ACCENT, label: str = ""):
    draw.line([(x, y0), (x, y1 - 22)], fill=color, width=3)
    head = [(x - 12, y1 - 22), (x + 12, y1 - 22), (x, y1 - 4)]
    draw.polygon(head, fill=color)
    if label:
        font = _font("JetBrainsMono-Regular.ttf", 18)
        bbox = font.getbbox(label)
        lw = bbox[2] - bbox[0]
        pad_x, pad_y = 12, 5
        midy = (y0 + y1) // 2
        bg_x0 = x + 24
        bg_y0 = midy - 14
        bg_x1 = bg_x0 + lw + 2 * pad_x
        bg_y1 = bg_y0 + 28 + 2
        draw.rounded_rectangle([bg_x0, bg_y0, bg_x1, bg_y1], radius=6,
                               fill=PANEL_2, outline=LINE, width=1)
        draw.text((bg_x0 + pad_x, bg_y0 + pad_y - 1), label, font=font, fill=DIM)


def _section_header(draw, x, y, num: str, title: str):
    num_font = _font("JetBrainsMono-Medium.ttf", 20)
    title_font = _font("JetBrainsMono-Bold.ttf", 28)
    draw.text((x, y), num, font=num_font, fill=ACCENT)
    nbbox = num_font.getbbox(num)
    nwidth = nbbox[2] - nbbox[0]
    draw.text((x + nwidth + 16, y - 2), title, font=title_font, fill=TEXT)


def _line(draw, x, y, text, color=TEXT, mono=True, size=22):
    font = _font("JetBrainsMono-Regular.ttf" if mono else "JetBrainsMono-Medium.ttf", size)
    draw.text((x, y), text, font=font, fill=color)


def build() -> Path:
    img = _radial_gradient((W, H), (int(W * 0.85), int(H * 0.08)),
                           (22, 36, 59), BG, radius=1200)
    img = img.filter(ImageFilter.GaussianBlur(radius=1.5))
    draw = ImageDraw.Draw(img, "RGBA")

    # Title strip
    title_font = _font("JetBrainsMono-Bold.ttf", 36)
    sub_font = _segoe(22)
    draw.text((PAD_X, 60), "WARDEN", font=title_font, fill=TEXT)
    bbox = title_font.getbbox("WARDEN")
    draw.text((PAD_X + (bbox[2] - bbox[0]) + 24, 73),
              "architecture", font=sub_font, fill=DIM)
    pill_font = _font("JetBrainsMono-Medium.ttf", 14)
    pill_text = "AGENT-RELIABILITY SUPERVISOR"
    pbox = pill_font.getbbox(pill_text)
    px0, py0 = PAD_X, 110
    px1 = px0 + (pbox[2] - pbox[0]) + 28
    py1 = py0 + (pbox[3] - pbox[1]) + 14
    draw.rounded_rectangle([px0, py0, px1, py1], radius=4, outline=(*DIM, 160), width=1)
    draw.text((px0 + 14, py0 + 5), pill_text, font=pill_font, fill=DIM)

    # Layer geometry
    panel_w = W - 2 * PAD_X
    layer_x0 = PAD_X
    layer_x1 = W - PAD_X
    layer_h = [170, 190, 380, 190, 170]
    gap = 60
    y_top = 180
    centers_x = (layer_x0 + layer_x1) // 2

    arrows_labels = [
        "OpenTelemetry / OTLP / HTTP",
        "list_problems · execute_dql · chat_with_davis_copilot",
        "governed action plan (with human-in-the-loop gate)",
        "measured outcome ledger",
    ]

    layers = []
    cy = y_top
    for h in layer_h:
        layers.append((cy, cy + h))
        cy += h + gap

    # 01 SUBJECTS: Worker Agent Fleet
    y0, y1 = layers[0]
    _panel(draw, layer_x0, y0, layer_x1, y1)
    _section_header(draw, layer_x0 + 28, y0 + 22,
                    "01 /", "Subjects: Worker Agent Fleet")
    box_y = y0 + 78
    box_w = 350
    box_h = 60
    gap_x = (panel_w - box_w * 3) // 4
    for i, name in enumerate(["refund-agent", "pricing-agent", "inventory-agent"]):
        bx0 = layer_x0 + gap_x + i * (box_w + gap_x)
        bx1 = bx0 + box_w
        draw.rounded_rectangle([bx0, box_y, bx1, box_y + box_h], radius=12,
                               fill=PANEL_2, outline=ACCENT, width=2)
        name_font = _font("JetBrainsMono-Medium.ttf", 22)
        nbbox = name_font.getbbox(name)
        nx = bx0 + (box_w - (nbbox[2] - nbbox[0])) // 2
        ny = box_y + (box_h - 28) // 2
        draw.text((nx, ny), name, font=name_font, fill=TEXT)
    _line(draw, layer_x0 + 28, y1 - 38,
          "loaded from warden/agents/fleet_config.json  ·  scales to N agents",
          color=DIM, size=18)

    # 02 SENSES: Dynatrace Platform
    y0, y1 = layers[1]
    _panel(draw, layer_x0, y0, layer_x1, y1)
    _section_header(draw, layer_x0 + 28, y0 + 22,
                    "02 /", "Senses: Dynatrace Platform (via MCP Server)")
    _line(draw, layer_x0 + 28, y0 + 80,
          "Distributed Tracing  ·  Davis Copilot  ·  DQL queries  ·  Problems",
          color=TEXT, size=22)
    _line(draw, layer_x0 + 28, y0 + 118,
          "@dynatrace-oss/dynatrace-mcp-server v1.8.6  (stdio + mcp Python SDK)",
          color=DIM, size=20)
    _line(draw, layer_x0 + 28, y0 + 150,
          "tool_filter: list_problems / execute_dql / chat_with_davis_copilot / create_workflow_for_notification",
          color=DIM, size=18)

    # 03 SUPERVISOR: Warden (the big box, two-column split)
    y0, y1 = layers[2]
    _panel(draw, layer_x0, y0, layer_x1, y1)
    _section_header(draw, layer_x0 + 28, y0 + 22,
                    "03 /", "Supervisor: Warden")
    # Two-column split inside
    inner_pad = 30
    col_top = y0 + 90
    col_bot = y1 - 130
    col_w = (panel_w - inner_pad * 3) // 2
    # Left: Gemini 3 brain (gold accent)
    lx0 = layer_x0 + inner_pad
    lx1 = lx0 + col_w
    draw.rounded_rectangle([lx0, col_top, lx1, col_bot], radius=14,
                           fill=PANEL_2, outline=GOLD, width=2)
    h_font = _font("JetBrainsMono-Bold.ttf", 26)
    draw.text((lx0 + 24, col_top + 18), "Gemini 3 brain", font=h_font, fill=GOLD)
    _line(draw, lx0 + 24, col_top + 64, "judgment over messy context",
          color=TEXT, size=20)
    bullets_l = [
        "failure_class · severity (1-5)",
        "blast_radius_usd · reversible",
        "recommended_action",
        "structured output (Gemini schema)",
        "temperature 0 · deterministic floor",
    ]
    for i, b in enumerate(bullets_l):
        _line(draw, lx0 + 30, col_top + 102 + i * 30, "· " + b,
              color=DIM, size=18)
    # Right: Python policy (cyan accent)
    rx0 = lx1 + inner_pad
    rx1 = rx0 + col_w
    draw.rounded_rectangle([rx0, col_top, rx1, col_bot], radius=14,
                           fill=PANEL_2, outline=ACCENT, width=2)
    draw.text((rx0 + 24, col_top + 18), "Python policy", font=h_font, fill=ACCENT)
    _line(draw, rx0 + 24, col_top + 64, "deterministic math + gates",
          color=TEXT, size=20)
    bullets_r = [
        "dollar exposure ($ recovered / lost / prevented)",
        "reversibility flag · severity floor",
        "human-approval gate for irreversible",
        "audit log (SHA-256 hashes, never raw)",
        "kill switch (WARDEN_DISABLE_GENERATIVE)",
    ]
    for i, b in enumerate(bullets_r):
        _line(draw, rx0 + 30, col_top + 102 + i * 30, "· " + b,
              color=DIM, size=18)
    # Loop strip at the bottom of the supervisor panel
    strip_y = y1 - 100
    strip_font = _font("JetBrainsMono-Bold.ttf", 22)
    flow = "SENSE  ->  REASON  ->  DECIDE  ->  ACT  ->  PROVE"
    fbbox = strip_font.getbbox(flow)
    fw = fbbox[2] - fbbox[0]
    fx = layer_x0 + (panel_w - fw) // 2
    draw.text((fx, strip_y), flow, font=strip_font, fill=ACCENT)
    _line(draw, layer_x0 + 28, y1 - 42,
          "the brain handles judgment, deterministic Python handles money math (defeats OWASP LLM06 Excessive Agency)",
          color=DIM, size=16)

    # 04 HANDS
    y0, y1 = layers[3]
    _panel(draw, layer_x0, y0, layer_x1, y1)
    _section_header(draw, layer_x0 + 28, y0 + 22,
                    "04 /", "Hands: Action Layer")
    actions = ["pause", "rollback", "alert", "open Dynatrace workflow"]
    a_y = y0 + 88
    a_x = layer_x0 + 30
    box_h = 46
    for label in actions:
        font = _font("JetBrainsMono-Medium.ttf", 22)
        bbox = font.getbbox(label)
        w_ = bbox[2] - bbox[0]
        pad = 18
        bx0 = a_x
        bx1 = bx0 + w_ + 2 * pad
        by0 = a_y
        by1 = a_y + box_h
        draw.rounded_rectangle([bx0, by0, bx1, by1], radius=10,
                               fill=PANEL_2, outline=GOOD, width=1)
        draw.text((bx0 + pad, by0 + 8), label, font=font, fill=GOOD)
        a_x = bx1 + 16
    _line(draw, layer_x0 + 28, y1 - 38,
          "human-in-the-loop approval is mandatory for irreversible / high-blast-radius actions",
          color=DIM, size=18)

    # 05 OUTPUT
    y0, y1 = layers[4]
    _panel(draw, layer_x0, y0, layer_x1, y1)
    _section_header(draw, layer_x0 + 28, y0 + 22,
                    "05 /", "Output: Measured Outcome")
    metrics = [
        ("MTTD",            "1-tick median"),
        ("$ recovered",     "honest sum"),
        ("$ irreversible",  "loss at detect"),
        ("$ prevented",     "estimated"),
    ]
    base_y = y0 + 80
    col_w = (panel_w - 60) // 4
    for i, (label, sub) in enumerate(metrics):
        x = layer_x0 + 30 + i * col_w
        lbl_font = _font("JetBrainsMono-Medium.ttf", 18)
        val_font = _font("JetBrainsMono-Bold.ttf", 22)
        draw.text((x, base_y), label, font=lbl_font, fill=DIM)
        draw.text((x, base_y + 30), sub, font=val_font,
                  fill=GOLD if "recovered" in label else (BAD if "irreversible" in label else TEXT))

    # Arrows between layers
    for i in range(4):
        y0a = layers[i][1] + 4
        y1a = layers[i + 1][0] - 4
        _arrow(draw, centers_x, y0a, y1a, color=ACCENT, label=arrows_labels[i])

    # Footer metadata
    foot_font = _font("JetBrainsMono-Regular.ttf", 16)
    meta = [
        "Dynatrace track  ·  Google Cloud Rapid Agent Hackathon",
        "Cloud Run hosted demo  ·  Apache-2.0",
    ]
    for i, m in enumerate(meta):
        bbox = foot_font.getbbox(m)
        w_ = bbox[2] - bbox[0]
        draw.text((W - PAD_X - w_, H - 70 + i * 24), m, font=foot_font, fill=DIM)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, "PNG", optimize=True)
    return OUT


if __name__ == "__main__":
    out = build()
    print(f"wrote {out}  ({out.stat().st_size / 1024:.1f} KB)")
