"""Render the zone screen at every resolution in resolutions.txt.

Renders both portrait and landscape for each entry through the ZoneScreen
plugin. Easier for testing new UI/layouts, so we can see which sizes already
work, which need tweaks or need to be dropped. Outputs PNGs and prints a summary.

NOTE: reinstall the plugin (`pip install ./plugins/screens/zone_screen`)
after editing its source before re-running, or your changes won't be visible.
Alternatively install with edit mode (-e flag on pip install)

Usage:
    python scripts/render_zone.py          # -> data/mockups/survey/
    python scripts/render_zone.py before   # -> data/mockups/before/
    python scripts/render_zone.py after    # -> data/mockups/after/
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

import vf_core
import zone_screen
from PIL import Image, ImageDraw
from vf_core.asset_manager import AssetManager

RES_FILE = Path(__file__).resolve().parent / "resolutions.txt"
ASSETS = Path(vf_core.__file__).resolve().parent / "assets"
# scripts/ lives directly under the vessel-frame checkout root.
REPO_ROOT = Path(__file__).resolve().parents[1]

PALETTE = {
    "background": "#FFFFFF", "foreground": "#FFFFFF", "line": "#000000",
    "text": "#000000", "icon": "#000000", "accent": "#FF0000",
}

# A well-populated vessel so every layout section has something to show.
VESSEL = {
    "identifier": "538008721", "name": "NORD ARCADIA", "ship_type_name": "Tanker",
    "ship_type": 80, "rate_of_turn": 0,
    "bow": 110, "stern": 50, "port": 14, "starboard": 14, "draught": 11.8,
    "lat": 51.953, "lon": 2.8166, "destination": "ROTTERDAM EUROPOORT",
    "eta": "16 May 04:00", "status": 0, "speed": 12.4, "course": 87, "heading": 85,
    "imo": "9778345", "callsign": "V7GH8",
}


class FakeRenderer:
    MIN_RENDER_INTERVAL = 0

    def __init__(self, w, h, out):
        self._canvas = Image.new("RGB", (w, h))
        self._out = out

    @property
    def canvas(self):
        return self._canvas

    @property
    def palette(self):
        return PALETTE

    def clear(self):
        ImageDraw.Draw(self._canvas).rectangle([(0, 0), self._canvas.size], fill=PALETTE["background"])

    async def flush(self):
        self._canvas.save(str(self._out), "png")


class FakeBus:
    def subscribe(self, topic):
        async def _gen():
            if False:
                yield None
        return _gen()


class FakeVM:
    def register_zone(self, *a, **k):
        pass


def parse_resolutions(path: Path):
    """Yield (w, h, devices) tuples from the resolutions file."""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"(\d+)\s*x\s*(\d+)\s*-\s*(.+)", line)
        if not m:
            continue
        yield int(m.group(1)), int(m.group(2)), m.group(3).strip()


def render_one(am, w, h, out):
    """Render one canvas, return (profile, scale, fits, error)."""
    r = FakeRenderer(w, h, out)
    try:
        screen = zone_screen.ZoneScreen(
            bus=FakeBus(), renderer=r, vm=FakeVM(), asset_manager=am,
            zone_name="zone", zone={"lat": 53.4, "lon": -3.0, "rad": 5800},
        )
        screen._current_vessel = VESSEL
        asyncio.run(screen._render())
        if screen._orientation == "landscape":
            # Landscape layouts scale by width and anchor header/footer, so they
            # cramp when the panel is wider than the design's aspect ratio.
            refs = {"compact": (600, 400), "standard": (800, 480), "large": (1600, 1200)}
            rw, rh = refs[screen._profile]
            fits = (w / h) <= (rw / rh) * 1.10
        else:
            # Whether the portrait min layout fits. The large profile has its own
            # sizing so report it as fitting.
            fits = screen._profile == "large" or screen._min_layout_height() <= h
        return screen._profile, round(screen._scale, 3), fits, None
    except Exception as exc:  # noqa: BLE001 - survey wants to see the error
        return "-", 0.0, False, f"{type(exc).__name__}: {exc}"


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "survey"
    out_dir = REPO_ROOT / "data" / "mockups" / mode
    out_dir.mkdir(parents=True, exist_ok=True)
    am = AssetManager(ASSETS)

    rows = []
    seen = set()
    for w, h, devices in parse_resolutions(RES_FILE):
        for cw, ch in {(w, h), (h, w)}:
            if (cw, ch) in seen:
                continue
            seen.add((cw, ch))
            orient = "portrait " if ch >= cw else "landscape"
            out = out_dir / f"survey_{cw}x{ch}.png"
            profile, scale, fits, error = render_one(am, cw, ch, out)
            rows.append((cw, ch, orient, profile, scale, fits, error, devices))

    rows.sort(key=lambda r: (r[0] * r[1], r[0]))
    print(f"\nRendered {len(rows)} canvases -> {out_dir}\n")
    print(f"{'resolution':>11}  {'orient':9}  {'profile':8}  {'scale':>5}  {'status':8}  devices")
    print("-" * 92)
    n_ok = n_tight = n_err = 0
    for cw, ch, orient, profile, scale, fits, error, devices in rows:
        if error:
            status = "ERROR"
            n_err += 1
        elif not fits:
            status = "OVERFLOW"
            n_tight += 1
        else:
            status = "ok"
            n_ok += 1
        note = error if error else devices
        print(f"{cw:>4}x{ch:<5}  {orient}  {profile:8}  {scale:>5}  {status:8}  {note}")
    print("-" * 92)
    print(f"{n_ok} ok   {n_tight} overflow   {n_err} error   of {len(rows)} canvases\n")


if __name__ == "__main__":
    sys.exit(main())
