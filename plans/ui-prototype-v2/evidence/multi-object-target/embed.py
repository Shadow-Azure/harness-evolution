"""Embed the eight before/after screenshots into the analysis HTML as data URIs.

The report is opened through a GUI preview card whose sandbox does not resolve
sibling files, so relative ``<img src>`` paths render as broken images. This
script inlines each PNG (downsampled to 1.25x of the CSS pixel size) so the
report is self-contained. ``--revert`` restores the relative paths so the HTML
stays editable without megabyte-long lines.

Usage:
    python embed.py            # relative paths -> data URIs (in place)
    python embed.py --revert   # data URIs -> relative paths (in place)
"""

from __future__ import annotations

import base64
import io
import re
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
HTML = HERE.parents[2] / "2026-11-26-multi-object-evolution-target-analysis.html"
REL = "ui-prototype-v2/evidence/multi-object-target/"
NAMES = (
    "before-target-form",
    "after-target-form",
    "before-wizard-step1",
    "after-wizard-step1",
    "before-run-scope",
    "after-run-scope",
    "before-run-workspace",
    "after-run-workspace",
)
# Screenshots are captured at 2x; 1.25x keeps UI text crisp at a third of the bytes.
SCALE = 0.625
DATA_SRC = re.compile(r'<img\s+src="data:image/png;base64,[A-Za-z0-9+/=]+"', re.DOTALL)


def embed() -> None:
    """Replace every relative screenshot path with an inlined data URI."""
    html = HTML.read_text(encoding="utf-8")
    total = 0
    for name in NAMES:
        relative = f'src="{REL}{name}.png"'
        if relative not in html:
            raise SystemExit(f"already embedded or missing: {relative}")
        with Image.open(HERE / f"{name}.png") as source:
            image = source.convert("RGB")
            width, height = image.size
            image = image.resize((round(width * SCALE), round(height * SCALE)), Image.LANCZOS)
            # UI screenshots have few colours; a 256-colour palette PNG is ~4x
            # smaller than RGB with no visible loss on crisp text.
            image = image.quantize(colors=256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
            buffer = io.BytesIO()
            image.save(buffer, "PNG", optimize=True)
        payload = buffer.getvalue()
        total += len(payload)
        data = base64.b64encode(payload).decode("ascii")
        html = html.replace(relative, f'src="data:image/png;base64,{data}"', 1)
        print(f"{name:24s} {width}x{height} -> {image.size[0]}x{image.size[1]}  {len(payload) // 1024} KB")
    HTML.write_text(html, encoding="utf-8", newline="\n")
    print(f"embedded {len(NAMES)} images ({total // 1024} KB raw) into {HTML.name}")


def revert() -> None:
    """Restore the relative screenshot paths in document order."""
    html = HTML.read_text(encoding="utf-8")
    matches = list(DATA_SRC.finditer(html))
    if len(matches) != len(NAMES):
        raise SystemExit(f"expected {len(NAMES)} embedded images, found {len(matches)}")
    for match, name in zip(reversed(matches), reversed(NAMES)):
        html = html[: match.start()] + f'<img src="{REL}{name}.png"' + html[match.end() :]
    HTML.write_text(html, encoding="utf-8", newline="\n")
    print(f"reverted {len(NAMES)} images to relative paths in {HTML.name}")


if __name__ == "__main__":
    if "--revert" in sys.argv[1:]:
        revert()
    else:
        embed()
