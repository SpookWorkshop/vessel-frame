"""Render the MapScreen plugin at all 6 resolutions for verification."""
from __future__ import annotations
import asyncio
import sys
import time
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

import vf_core
import map_screen
from vf_core.asset_manager import AssetManager

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "data" / "mockups"
TMP = OUT / "_maptmp"
_CACHE = REPO_ROOT / "data" / "map_cache"
TILE = next(iter(sorted(_CACHE.glob("map_landscape_*"))), None)
PALETTE = {
    "background": "#FFFFFF", "foreground": "#FFFFFF", "line": "#000000",
    "text": "#000000", "icon": "#000000", "accent": "#FF0000",
}

# Liverpool-ish bounds matching the test cached tile area (update if you're testing elsewhere).
BOUNDS = {"min_lat": 53.35, "max_lat": 53.47, "min_lon": -3.05, "max_lon": -2.92}

NOW = time.time()
# name, type, lat, lon, heading(None=no heading), speed, secs-ago, bow, stern, beam
FLEET = [
    ("ATLANTIC VIRTUE", "Tanker", 53.430, -2.995, 20, 21.8, 0, 250, 116, 60),
    ("NORD ARCADIA", "Tanker", 53.418, -3.000, 200, 12.4, 22, 120, 63, 32),
    ("FAIR ISLE", "Passenger Ship", 53.410, -2.990, None, 0.0, 41, 75, 45, 20),
    ("BOY ANDREW", "Fishing", 53.402, -2.998, 0, 0.0, 64, 11, 7, 6),
    ("BREMEN EXPRESS", "Cargo", 53.395, -2.985, 30, 15.7, 70, 200, 120, 40),
    ("SVITZER WARDEN", "Tug", 53.388, -3.005, 95, 8.1, 128, 20, 12, 10),
    ("GLOMAR ENDURANCE", "Dredger", 53.440, -3.020, 270, 1.2, 305, 60, 30, 18),
    ("GANNET", "Fishing", 53.412, -2.965, None, 0.0, 430, 10, 6, 5),
    ("FRISIA", "Pleasure Craft", 53.375, -2.955, 110, 6.8, 500, 8, 4, 4),
    ("PIONEER OF AYR", "Fishing", 53.378, -3.030, 305, 6.2, 720, 13, 7, 6),
    ("OCEAN HARMONY", "Tanker", 53.448, -2.975, 150, 14.1, 900, 180, 90, 32),
    ("VICTORIA", "Passenger Ship", 53.360, -2.978, 60, 0.0, 1620, 90, 50, 22),
    ("EDGE RUNNER", "Cargo", 53.469, -2.922, 45, 10.0, 10, 220, 130, 44),  # top-right corner
]
VESSELS = [
    {"name": n, "ship_type_name": t, "lat": lat, "lon": lon, "heading": hd,
     "speed": sp, "ts": NOW - off, "bow": bow, "stern": stern,
     "port": beam // 2, "starboard": beam - beam // 2, "identifier": "232000000"}
    for n, t, lat, lon, hd, sp, off, bow, stern, beam in FLEET
]


class FakeRenderer:
    MIN_RENDER_INTERVAL = 0

    def __init__(self, w, h, out):
        self._c = Image.new("RGB", (w, h))
        self._out = out

    @property
    def canvas(self):
        return self._c

    @property
    def palette(self):
        return PALETTE

    def clear(self):
        ImageDraw.Draw(self._c).rectangle([(0, 0), self._c.size], fill=PALETTE["background"])

    async def flush(self):
        self._c.save(str(self._out), "png")


class FakeBus:
    def subscribe(self, topic):
        async def _gen():
            if False:
                yield None
        return _gen()


class FakeVM:
    def get_recent_vessels(self, limit=20):
        return list(VESSELS)[:limit]


def main():
    if TILE is None:
        print(f"No cached tile found in {_CACHE}. Map render needs a cached plate.")
        return
    mode = sys.argv[1] if len(sys.argv) > 1 else "map"
    out_dir = OUT / mode
    am = AssetManager(Path(vf_core.__file__).resolve().parent / "assets")
    tile = Image.open(TILE).convert("RGB")
    out_dir.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(exist_ok=True)
    sizes = [
        (400, 600, "p4"), (480, 800, "p7"), (1200, 1600, "p13"),
        (600, 400, "l4"), (800, 480, "l7"), (1600, 1200, "l13"),
    ]
    for w, h, tag in sizes:
        out = out_dir / f"map_real_{tag}.png"
        screen = map_screen.MapScreen(
            bus=FakeBus(), renderer=FakeRenderer(w, h, out), vm=FakeVM(),
            asset_manager=am, data_dir=TMP, bounds=BOUNDS, mapbox_api_key="",
        )
        # inject the cached tile as the plate (no API key to fetch).
        if hasattr(screen, "_tiles"):
            screen._tiles._portrait = tile
            screen._tiles._landscape = tile
        else:
            screen._map_portrait = tile
            screen._map_landscape = tile
        asyncio.run(screen._render())
        print(f"{w}x{h} -> {out.name}")
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    main()
