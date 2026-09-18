#!/usr/bin/env python3
"""Render the README header (logo + wordmark table) as a single SVG file.

Replaces the two-cell HTML table in README.md:
    <img src=".github/assets/logo.svg" width="64"> + "ROLEPLAY AGENT" (52px/900)
with one flat, vertically-centered SVG so it renders identically everywhere
GitHub's <table> styling gets stripped (e.g. some markdown viewers).

Usage:
    python scripts/generate_header_svg.py [output.svg]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from PIL import ImageFont

REPO_ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = REPO_ROOT / ".github/assets/logo.svg"
DEFAULT_OUTPUT = REPO_ROOT / ".github/assets/header.svg"

TEXT = "ROLEPLAY AGENT"
FONT_SIZE = 52
FONT_WEIGHT = 900
ICON_SIZE = 64
GAP = 20  # space between icon and text, matching the table's cell padding
# Arial Black is the closest local match to a generic sans-serif at
# font-weight: 900 - used only to measure text width so the canvas can be
# cropped tight, same as the original inline-table layout.
MEASURE_FONT = "/System/Library/Fonts/Supplemental/Arial Black.ttf"


def _extract_paths(logo_svg: str) -> tuple[str, list[str]]:
    fill = re.search(r'fill="([^"]+)"', logo_svg).group(1)
    paths = re.findall(r'<path d="([^"]+)"', logo_svg)
    return fill, paths


def _text_width(text: str, size: int) -> int:
    font = ImageFont.truetype(MEASURE_FONT, size)
    left, top, right, bottom = font.getbbox(text)
    return right - left


def generate(output_path: Path) -> None:
    logo_svg = LOGO_PATH.read_text()
    fill, paths = _extract_paths(logo_svg)

    text_width = _text_width(TEXT, FONT_SIZE)
    width = ICON_SIZE + GAP + text_width
    height = max(ICON_SIZE, FONT_SIZE + 10)

    icon_y = (height - ICON_SIZE) / 2
    text_x = ICON_SIZE + GAP
    text_y = height / 2

    path_elements = "\n    ".join(f'<path d="{d}" />' for d in paths)

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <g transform="translate(0, {icon_y})">
    <svg width="{ICON_SIZE}" height="{ICON_SIZE}" viewBox="0 0 64 64" fill="{fill}">
    {path_elements}
    </svg>
  </g>
  <text x="{text_x}" y="{text_y}" dominant-baseline="central"
        font-family="Arial, Helvetica, sans-serif" font-size="{FONT_SIZE}"
        font-weight="{FONT_WEIGHT}" white-space="pre">{TEXT}</text>
</svg>
"""
    output_path.write_text(svg)
    print(f"wrote {output_path} ({width}x{height})")


def main() -> None:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    generate(output)


if __name__ == "__main__":
    main()
