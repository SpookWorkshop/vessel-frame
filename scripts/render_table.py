"""Render the TableScreen plugin at the three main resolutions."""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import table_screen
import vf_core
from PIL import Image, ImageDraw
from vf_core.asset_manager import AssetManager

OUT = Path(__file__).resolve().parents[1] / "data" / "mockups"
PALETTE = {
    "background": "#FFFFFF", "foreground": "#FFFFFF", "line": "#000000",
    "text": "#000000", "icon": "#000000", "accent": "#FF0000",
}

NOW = time.time()
# name, type, status, speed, course, secs-ago, mmsi, bow, stern, beam
FLEET = [
    ("ATLANTIC VIRTUE", "Tanker - Hazardous A", 0, 21.8, 67, 0,   "232028316", 250, 116, 60),
    ("NORD ARCADIA", "Tanker", 0, 12.4, 90, 22,                   "538008721", 120, 63, 32),
    ("FAIR ISLE", "Passenger Ship", 5, 0.0, 0, 41,                "232118900", 75, 45, 20),
    ("BOY ANDREW", "Fishing", 1, 0.0, 0, 64,                      "250004410", 11, 7, 6),
    ("BREMEN EXPRESS", "Cargo - Hazardous A", 0, 15.7, 95, 70,    "211457000", 200, 120, 40),
    ("NORTHERN STAR", "Sailing", 8, 5.4, 215, 128,               "244813000", 9, 5, 4),
    ("AMSTELDIEP", "Tug", 0, 8.1, 32, 190,                        "244017000", 20, 12, 10),
    ("GLOMAR ENDURANCE", "Dredger", 0, 1.2, 5, 305,               "257038000", 60, 30, 18),
    ("GANNET", "Fishing", 1, 0.0, 0, 430,                         "232556000", 10, 6, 5),
    ("FRISIA", "High Speed Craft", 0, 6.8, 110, 500,             "211223400", 35, 10, 8),
    ("PIONEER OF AYR", "Fishing", 0, 6.2, 295, 720,              "232889100", 13, 7, 6),
]
VESSELS = [
    {"name": n, "ship_type_name": t, "status": st, "speed": sp, "course": crs,
     "ts": NOW - off, "identifier": mmsi, "bow": bow, "stern": stern,
     "port": beam // 2, "starboard": beam - beam // 2}
    for n, t, st, sp, crs, off, mmsi, bow, stern, beam in FLEET
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
        return sorted(VESSELS, key=lambda v: v.get("ts", 0), reverse=True)[:limit]


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "table"
    out_dir = OUT / mode
    out_dir.mkdir(parents=True, exist_ok=True)
    am = AssetManager(Path(vf_core.__file__).resolve().parent / "assets")
    sizes = [
        (400, 600, "p4"), (480, 800, "p7"), (1200, 1600, "p13"),   # portrait
        (600, 400, "l4"), (800, 480, "l7"), (1600, 1200, "l13"),   # landscape
    ]
    for w, h, tag in sizes:
        out = out_dir / f"table_real_{tag}.png"
        r = FakeRenderer(w, h, out)
        screen = table_screen.TableScreen(
            bus=FakeBus(), renderer=r, vm=FakeVM(), asset_manager=am,
        )
        asyncio.run(screen._render())
        print(f"{w}x{h} {screen._orientation}/{screen._profile} "
              f"scale={screen._scale:.3f} -> {out.name}")


if __name__ == "__main__":
    main()
