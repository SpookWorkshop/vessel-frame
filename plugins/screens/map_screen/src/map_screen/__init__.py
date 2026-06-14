"""Map screen plugin for vessel-frame.

Displays vessels over a Mapbox map image (downloaded and cached locally) inside
a broadsheet frame: a masthead band on top, the map as a bordered plate, and a
footer band with a marker legend and attribution. Vessels are heading-oriented
markers (to-scale hull when zoomed in, else a chevron, else a dot), each with a
white halo and a solid/hollow fill for under-way/moored. Names are decluttered.

All colours come from the renderer palette (never hard-coded) so the screen
degrades gracefully across reduced-colour and greyscale panels; meaning is
carried by shape, fill-state and halo, never by colour alone.
"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import math
import time
import urllib.request
from contextlib import suppress
from pathlib import Path
from typing import Any

import logging
from PIL import Image, ImageDraw, ImageFont

from vf_core.asset_manager import AssetManager
from vf_core.message_bus import MessageBus
from vf_core.plugin_types import (
    ConfigField,
    ConfigFieldType,
    ConfigSchema,
    RendererPlugin,
    ScreenPlugin,
    require_plugin_args,
)
from vf_core.render_strategies import PeriodicRenderStrategy
from vf_core.text_utils import TextRenderingMixin
from vf_core.vessel_manager import VesselManager

ISSUE_NO = "No. 0183"

# Recency buckets (seconds) used to prioritise which labels win a collision.
LIVE_MAX = 60
RECENT_MAX = 300


class MapScreen(ScreenPlugin, TextRenderingMixin):
    """Screen to display a map of vessels which were recently observed."""

    # Hull pixel clamps. Every vessel draws as a hull, sized to-scale from its
    # dimensions but never below the minimum (so small craft read as a min-size
    # hull rather than switching to a different marker style).
    SHIP_MIN_LENGTH_PX = 14
    SHIP_MAX_LENGTH_PX = 80
    SHIP_MIN_BEAM_PX = 6
    SHIP_MAX_BEAM_PX = 30

    DOWNLOAD_TIMEOUT: float = 30.0
    # Mapbox Static Images API caps each edge at 1280px; larger plates use @2x.
    MAPBOX_MAX_EDGE: int = 1280

    def __init__(
        self,
        *,
        bus: MessageBus,
        renderer: RendererPlugin,
        vm: VesselManager,
        asset_manager: AssetManager,
        in_topic: str = "vessel.updated",
        update_interval: float = 300.0,
        bounds: dict | None = None,
        data_dir: Path,
        map_style: str = "mapbox/light-v11",
        mapbox_api_key: str = "",
        **kwargs: Any,
    ) -> None:
        require_plugin_args(bus=bus, renderer=renderer, vm=vm, asset_manager=asset_manager)
        self._logger = logging.getLogger(__name__)

        self._bus = bus
        self._renderer = renderer
        self._vessel_manager = vm
        self._asset_manager = asset_manager
        self._in_topic = in_topic
        self._task: asyncio.Task[None] | None = None
        self._palette = renderer.palette
        self._map_style = map_style.removeprefix("mapbox://styles/")
        self._cache_dir = data_dir / "map_cache"
        self._mapbox_key = mapbox_api_key

        if len(self._mapbox_key) == 0:
            self._logger.warning("Mapbox API Key not set. Map backgrounds may be unavailable")

        # --- parse bounds ---
        bounds_keys = ("min_lat", "max_lat", "min_lon", "max_lon")
        if bounds and not all(k in bounds for k in bounds_keys):
            self._logger.warning(
                f"Map bounds config is missing required keys "
                f"{[k for k in bounds_keys if k not in bounds]}. Bounds will be ignored."
            )
            bounds = None
        self._min_lat = float(bounds["min_lat"]) if bounds else 0.0
        self._max_lat = float(bounds["max_lat"]) if bounds else 0.0
        self._min_lon = float(bounds["min_lon"]) if bounds else 0.0
        self._max_lon = float(bounds["max_lon"]) if bounds else 0.0
        self._bounds_valid = (
            self._max_lat > self._min_lat and self._max_lon > self._min_lon
        )
        if not self._bounds_valid:
            self._logger.warning(
                "Map bounds are not configured or invalid. Set the bounds field in "
                "config. Vessels will not be drawn until bounds are configured."
            )

        # --- scale, fonts, chrome + marker metrics (needed before fetch, since
        #     the plate size determines the requested image dimensions) ---
        canvas_w, canvas_h = self._renderer.canvas.size
        self._scale = max(1.0, min(canvas_w, canvas_h) / 480)
        self._margin = self._px(18)
        self._thick = self._px(2)
        self._line_w = max(1, self._px(2))

        self._fonts: dict[str, ImageFont.FreeTypeFont] = {
            "brand": asset_manager.get_font("secondary", "SemiBold", self._px(13)),
            "meta": asset_manager.get_font("secondary", "Regular", self._px(11)),
            "section": asset_manager.get_font("secondary", "SemiBold", self._px(12)),
            "label": asset_manager.get_font("primary", "700", self._px(11)),
            "attr": asset_manager.get_font("secondary", "Regular", self._px(9)),
        }

        self._halo_w = max(2, self._px(3))
        self._marker_outline = max(1, self._px(2))
        self._dot_r = max(2, self._px(4))
        self._dot_halo = max(1, self._px(1))  # subtler than the polygon halo
        self._label_gap = self._px(7)

        # --- cache + download map images at plate size for both orientations ---
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_key = self._compute_cache_key()
        self._cleanup_stale_cache()
        self._ensure_map_images()
        self._map_portrait = self._load_map_image("map_portrait")
        self._map_landscape = self._load_map_image("map_landscape")

        interval = float(update_interval) if isinstance(update_interval, str) else update_interval
        self._render_strategy = PeriodicRenderStrategy(
            self._render, max(interval, renderer.MIN_RENDER_INTERVAL)
        )

    def _px(self, v: float) -> int:
        return max(1, round(v * self._scale))

    # --- layout ------------------------------------------------------------
    def _layout(self, w: int, h: int) -> dict[str, Any]:
        """Resolve the broadsheet frame for a canvas of size (w, h).

        Single source of truth for chrome y-positions and the map plate rect,
        used by both rendering and the (pre-fetch) plate-size calculation.
        """
        px = self._px
        f = self._fonts
        m = self._margin
        brand_y = m
        rule1_y = brand_y + self._line_height(f["brand"]) + px(6)
        eyebrow_y = rule1_y + self._thick + px(6)
        plate_top = eyebrow_y + self._line_height(f["section"]) + px(8)

        footer_text_y = h - m - self._line_height(f["attr"])
        rule2_y = footer_text_y - px(6)
        plate_bottom = rule2_y - px(8)

        return {
            "brand_y": brand_y, "rule1_y": rule1_y, "eyebrow_y": eyebrow_y,
            "rule2_y": rule2_y, "footer_text_y": footer_text_y,
            "plate": (m, plate_top, w - m, plate_bottom),
        }

    def _plate_size(self, canvas_w: int, canvas_h: int) -> tuple[int, int]:
        """Pixel size of the map plate for a given canvas size."""
        x0, y0, x1, y1 = self._layout(canvas_w, canvas_h)["plate"]
        return max(1, x1 - x0), max(1, y1 - y0)

    # --- cache + download --------------------------------------------------
    def _compute_cache_key(self) -> str:
        """Short hash of the params that affect the map image (bounds, style,
        plate size). Plate dims are normalised to [short, long] so flipping
        orientation reuses the same entries."""
        canvas = self._renderer.canvas
        pw, ph = self._plate_size(canvas.width, canvas.height)
        short_edge, long_edge = min(pw, ph), max(pw, ph)
        key_data = (
            f"{self._min_lat}:{self._max_lat}:{self._min_lon}:{self._max_lon}"
            f":{self._map_style}:{short_edge}x{long_edge}"
        )
        return hashlib.sha256(key_data.encode()).hexdigest()[:12]

    def _cleanup_stale_cache(self) -> None:
        """Remove cached map files that don't match the current cache key."""
        for path in self._cache_dir.iterdir():
            if path.name.startswith(("map_portrait_", "map_landscape_")) and \
                    not path.name.endswith(f"_{self._cache_key}"):
                self._logger.info(f"Removing stale cache file: {path.name}")
                path.unlink(missing_ok=True)

    def _ensure_map_images(self) -> None:
        """Download plate-sized map images for both orientations if missing."""
        if not self._bounds_valid:
            return

        canvas = self._renderer.canvas
        short_edge = min(canvas.width, canvas.height)
        long_edge = max(canvas.width, canvas.height)

        # Portrait canvas is (short x long); landscape is (long x short).
        portrait_plate = self._plate_size(short_edge, long_edge)
        landscape_plate = self._plate_size(long_edge, short_edge)
        orientations = [
            ("map_portrait", *portrait_plate),
            ("map_landscape", *landscape_plate),
        ]

        for name, width, height in orientations:
            img_path = self._cache_dir / f"{name}_{self._cache_key}"
            if self._is_valid_image(img_path):
                continue
            if len(self._mapbox_key) == 0:
                self._logger.error("No Mapbox Key set - unable to download image")
                continue

            req_w, req_h, retina = self._compute_request_params(width, height)
            self._logger.info(f"Downloading map image: {name}")
            try:
                bounds = (
                    f"[{self._min_lon},{self._min_lat},"
                    f"{self._max_lon},{self._max_lat}]"
                )
                url = (
                    f"https://api.mapbox.com/styles/v1/{self._map_style}/static/"
                    f"{bounds}/{req_w}x{req_h}{retina}?access_token={self._mapbox_key}"
                )
                self._logger.debug(f"Mapbox URL: {url}")
                tmp_path = img_path.with_suffix(".tmp")
                try:
                    with urllib.request.urlopen(url, timeout=self.DOWNLOAD_TIMEOUT) as response:
                        tmp_path.write_bytes(response.read())
                    tmp_path.replace(img_path)
                except Exception:
                    tmp_path.unlink(missing_ok=True)
                    raise
                self._logger.info(f"Downloaded map image: {img_path}")
            except Exception:
                self._logger.exception(f"Failed to download map image: {name}")

    def _compute_request_params(self, width: int, height: int) -> tuple[int, int, str]:
        """Return (request_width, request_height, retina_suffix) for a Mapbox URL.

        Mapbox caps each dimension at 1280. When either edge exceeds that we use
        @2x: dimension params are halved and Mapbox returns a 2x-density image,
        so the final pixel size matches the plate exactly.
        """
        if max(width, height) > self.MAPBOX_MAX_EDGE:
            req_w = (width + 1) // 2
            req_h = (height + 1) // 2
            if max(req_w, req_h) > self.MAPBOX_MAX_EDGE:
                self._logger.warning(
                    f"Plate dimensions {width}x{height} exceed Mapbox @2x limit. "
                    f"Image may be truncated or rejected."
                )
            return req_w, req_h, "@2x"
        return width, height, ""

    def _is_valid_image(self, path: Path) -> bool:
        """True if the file exists and can be fully decoded; deletes if corrupt."""
        if not path.exists():
            return False
        try:
            with Image.open(path) as img:
                img.load()
            return True
        except Exception:
            self._logger.warning(f"Cached map image is corrupt, deleting: {path.name}")
            path.unlink(missing_ok=True)
            return False

    def _load_map_image(self, name: str) -> Image.Image | None:
        """Load a cached map image (RGB) for compositing."""
        path = self._cache_dir / f"{name}_{self._cache_key}"
        if not self._is_valid_image(path):
            self._logger.warning(f"Map image not found: {path.name}")
            return None
        with Image.open(path) as img:
            img.load()
            return img.convert("RGB")

    def _get_current_map(self) -> Image.Image | None:
        """The plate-sized map image for the current canvas orientation."""
        canvas = self._renderer.canvas
        is_portrait = canvas.width < canvas.height
        return self._map_portrait if is_portrait else self._map_landscape

    # --- lifecycle ---------------------------------------------------------
    async def activate(self) -> None:
        """Start listening for updates and enable periodic rendering."""
        if self._task and not self._task.done():
            return
        if self._map_portrait is None or self._map_landscape is None:
            self._ensure_map_images()
            self._map_portrait = self._load_map_image("map_portrait")
            self._map_landscape = self._load_map_image("map_landscape")

        await self._render_strategy.start()
        self._render_strategy.request_render()
        self._task = asyncio.create_task(self._update_loop())

    async def deactivate(self) -> None:
        """Stop listening for updates and cancel pending work."""
        if self._task and not self._task.done():
            await self._render_strategy.stop()
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _update_loop(self) -> None:
        """Internal loop that receives update events and requests renders."""
        try:
            async for _ in self._bus.subscribe(self._in_topic):
                self._render_strategy.request_render()
        except asyncio.CancelledError:
            raise
        except Exception:
            self._logger.exception("Update loop crashed")
            raise

    # --- render ------------------------------------------------------------
    async def _render(self) -> None:
        """Render the map of recently observed vessels inside the broadsheet frame."""
        canvas = self._renderer.canvas
        draw = ImageDraw.Draw(canvas)
        W, H = canvas.size
        layout = self._layout(W, H)
        plate = layout["plate"]
        px0, py0, px1, py1 = plate
        plate_w, plate_h = px1 - px0, py1 - py0

        self._renderer.clear()

        # --- build the map plate as a sub-image: markers/labels drawn here are
        #     hard-clipped to the plate by the paste, so nothing spills over the
        #     border or off the edge. ---
        current_map = self._get_current_map()
        if current_map is not None:
            plate_img = (current_map.resize((plate_w, plate_h))
                         if current_map.size != (plate_w, plate_h) else current_map.copy())
        else:
            plate_img = Image.new("RGB", (plate_w, plate_h), self._palette["background"])
        pdraw = ImageDraw.Draw(plate_img)

        markers: list[tuple[dict[str, Any], tuple[float, float]]] = []
        if self._bounds_valid:
            mpp = self._calculate_scale(plate_w, plate_h)
            for vessel in self._vessel_manager.get_recent_vessels():
                pos = self._project(vessel, plate_w, plate_h)
                if pos is None:
                    continue
                markers.append((vessel, pos))
                self._draw_marker(pdraw, vessel, pos, mpp)
            self._draw_labels(pdraw, markers, plate_w, plate_h)

        canvas.paste(plate_img, (px0, py0))
        draw.rectangle([px0, py0, px1, py1], outline=self._palette["line"], width=self._thick)

        # --- chrome (drawn last so it sits above the map) ---
        self._draw_masthead(draw, W, layout, len(markers))
        self._draw_footer(draw, W, layout)

        await self._renderer.flush()

    def _draw_masthead(self, draw: ImageDraw.ImageDraw, W: int, layout: dict, count: int) -> None:
        """Masthead band: brand / issue no / date, rule, and vessel-count eyebrow."""
        f = self._fonts
        x0, x1 = self._margin, W - self._margin
        text = self._palette["text"]
        line = self._palette["line"]
        # opaque band so text never fights the map
        draw.rectangle([0, 0, W, layout["plate"][1] - self._px(6)], fill=self._palette["background"])
        now = datetime.datetime.now()
        self._draw_text(draw, x0, layout["brand_y"], "VESSEL FRAME", f["brand"], fill=text)
        self._draw_text(draw, (x0 + x1) // 2, layout["brand_y"], ISSUE_NO, f["meta"],
                        halign="centre", fill=text)
        self._draw_text(draw, x1, layout["brand_y"], now.strftime("%d %b  %H:%M"),
                        f["meta"], halign="right", fill=text)
        draw.line([(x0, layout["rule1_y"]), (x1, layout["rule1_y"])], line, self._thick)
        self._draw_text(draw, x0, layout["eyebrow_y"], f"{count} VESSELS ON THE WATER",
                        f["section"], fill=text)

    def _draw_footer(self, draw: ImageDraw.ImageDraw, W: int, layout: dict) -> None:
        """Footer band: marker legend (under way / moored) + map attribution."""
        f = self._fonts
        x0, x1 = self._margin, W - self._margin
        line = self._palette["line"]
        attr_h = self._line_height(f["attr"])
        ry, ty = layout["rule2_y"], layout["footer_text_y"]
        # opaque band from just above the rule to the bottom edge
        band_bottom = ty + attr_h + self._margin
        draw.rectangle([0, ry - self._px(4), W, band_bottom], fill=self._palette["background"])
        draw.line([(x0, ry), (x1, ry)], line, self._thick)
        cy = ty + attr_h // 2
        self._legend_hull(draw, x0 + self._px(6), cy, True)
        _, _, w1 = self._draw_text(draw, x0 + self._px(14), ty, "under way", f["attr"])
        lx = x0 + self._px(14) + w1 + self._px(14)
        self._legend_hull(draw, lx + self._px(6), cy, False)
        self._draw_text(draw, lx + self._px(14), ty, "moored", f["attr"])
        self._draw_text(draw, x1, ty, "© Mapbox  © OpenStreetMap", f["attr"], halign="right")

    # --- projection + vessel helpers --------------------------------------
    def _project(self, vessel: dict[str, Any], plate_w: int, plate_h: int) -> tuple[float, float] | None:
        """Project a vessel's lat/lon to plate-relative pixel coords, or None if
        out of bounds. Coords are relative to the plate sub-image origin."""
        lat, lon = vessel.get("lat"), vessel.get("lon")
        if lat is None or lon is None:
            return None
        if not (self._min_lat <= lat <= self._max_lat):
            return None
        if not (self._min_lon <= lon <= self._max_lon):
            return None
        x = ((lon - self._min_lon) / (self._max_lon - self._min_lon)) * plate_w
        y = plate_h - ((lat - self._min_lat) / (self._max_lat - self._min_lat)) * plate_h
        return x, y

    def _heading(self, vessel: dict[str, Any]) -> float | None:
        """Best available heading (true heading, else COG), or None if unavailable."""
        heading = vessel.get("true_heading") or vessel.get("heading")
        if heading is None or heading == 511:  # 511 = not available
            heading = vessel.get("cog")
        if heading is None or heading == 360:   # 360 = not available
            return None
        return float(heading)

    def _is_moving(self, vessel: dict[str, Any]) -> bool:
        """Under way (solid marker) vs moored/stopped (hollow)."""
        return vessel.get("speed", 0) > 0.5

    def _recency_rank(self, vessel: dict[str, Any], now: float) -> int:
        age = now - vessel.get("ts", 0)
        return 0 if age < LIVE_MAX else (1 if age < RECENT_MAX else 2)

    # --- markers -----------------------------------------------------------
    def _draw_marker(self, draw: ImageDraw.ImageDraw, vessel: dict[str, Any],
                     pos: tuple[float, float], mpp: float) -> None:
        """Hull (oriented by heading, min-clamped); dot when no heading is known."""
        x, y = pos
        moving = self._is_moving(vessel)
        heading = self._heading(vessel)
        if heading is None:
            self._draw_dot(draw, x, y, moving)
            return
        length = vessel.get("stern", 0) + vessel.get("bow", 0)
        beam = vessel.get("port", 0) + vessel.get("starboard", 0)
        self._draw_hull(draw, x, y, length, beam, heading, mpp, moving)

    def _fill_outline(self, moving: bool) -> tuple[str, str, int]:
        """(fill, outline, outline_width) for a marker: solid accent when under
        way, hollow (accent outline) when moored."""
        P = self._palette
        if moving:
            return P["accent"], P["line"], self._marker_outline
        return P["foreground"], P["accent"], max(self._marker_outline, self._px(2))

    def _polygon_with_halo(self, draw: ImageDraw.ImageDraw, pts: list, moving: bool) -> None:
        P = self._palette
        draw.polygon(pts, fill=P["foreground"], outline=P["foreground"], width=self._halo_w)
        fill, outline, w = self._fill_outline(moving)
        draw.polygon(pts, fill=fill, outline=outline, width=w)

    def _hull_points(self, x: float, y: float, length_px: float, beam_px: float,
                     heading: float) -> list[tuple[float, float]]:
        """Pointed-hull polygon (straight stern, pointed bow) centred at (x, y),
        oriented by heading (0 = north/up)."""
        half_l, half_b = length_px / 2, beam_px / 2
        bow = length_px * 0.25
        base = [
            (0, -half_l), (-half_b, -half_l + bow), (-half_b, half_l),
            (half_b, half_l), (half_b, -half_l + bow),
        ]
        rad = math.radians(heading)
        return [(x + bx * math.cos(rad) - by * math.sin(rad),
                 y + bx * math.sin(rad) + by * math.cos(rad)) for bx, by in base]

    def _draw_dot(self, draw: ImageDraw.ImageDraw, x: float, y: float, moving: bool) -> None:
        """Dot marker (no heading available) with a subtle halo + fill-state."""
        P = self._palette
        r, halo = self._dot_r, self._dot_halo
        draw.ellipse([x - r - halo, y - r - halo, x + r + halo, y + r + halo],
                     fill=P["foreground"])
        fill, outline, w = self._fill_outline(moving)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=fill, outline=outline, width=w)

    def _draw_hull(self, draw: ImageDraw.ImageDraw, x: float, y: float, length: int,
                   beam: int, heading: float, mpp: float, moving: bool) -> None:
        """Pointed hull, oriented by heading, sized to-scale but never below the
        minimum; vessels with no dimensions draw at the minimum hull size."""
        min_l, max_l = self.SHIP_MIN_LENGTH_PX * self._scale, self.SHIP_MAX_LENGTH_PX * self._scale
        min_b, max_b = self.SHIP_MIN_BEAM_PX * self._scale, self.SHIP_MAX_BEAM_PX * self._scale
        if length > 0 and beam > 0:
            length_px = max(min_l, min(max_l, length / mpp))
            beam_px = max(min_b, min(max_b, beam / mpp))
        else:
            length_px, beam_px = min_l, min_b
        self._polygon_with_halo(draw, self._hull_points(x, y, length_px, beam_px, heading), moving)

    def _legend_hull(self, draw: ImageDraw.ImageDraw, x: float, y: float, moving: bool) -> None:
        """Small north-pointing hull for the footer legend."""
        self._polygon_with_halo(draw, self._hull_points(x, y, self._px(13), self._px(6), 0), moving)

    # --- labels (declutter) ------------------------------------------------
    def _draw_labels(self, draw: ImageDraw.ImageDraw,
                     markers: list[tuple[dict[str, Any], tuple[float, float]]],
                     plate_w: int, plate_h: int) -> None:
        """Draw vessel names with a halo, skipping any that would collide. Labels
        are placed in significance order (most-recent, then largest) so the ones
        that win collisions are the ones that matter most. Coords are
        plate-relative (the caller composites the plate sub-image)."""
        now = time.time()
        f = self._fonts["label"]
        x0, y0, x1, y1 = 0, 0, plate_w, plate_h
        th = self._line_height(f)
        ordered = sorted(
            markers,
            key=lambda m: (self._recency_rank(m[0], now),
                           -(m[0].get("stern", 0) + m[0].get("bow", 0))),
        )
        placed: list[tuple[int, int, int, int]] = []
        for v, (x, y) in ordered:
            name = self._label_name(v)
            if not name:
                continue
            tw = self._text_width(f, name)
            lx = x + self._label_gap
            ly = y - th / 2
            if lx + tw > x1 - self._px(4):  # would overflow right -> place left
                lx = x - self._label_gap - tw
            box = (int(lx - self._px(2)), int(ly), int(lx + tw + self._px(2)), int(ly + th))
            if lx < x0 or box[1] < y0 or box[3] > y1:
                continue
            if any(self._overlaps(box, b) for b in placed):
                continue
            placed.append(box)
            self._halo_text(draw, lx, ly, name, f, self._palette["text"])

    @staticmethod
    def _overlaps(a: tuple, b: tuple) -> bool:
        return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])

    def _label_name(self, vessel: dict[str, Any]) -> str:
        name = vessel.get("name")
        if not name or name == "Unknown":
            name = vessel.get("identifier")
        return str(name) if name else ""

    def _halo_text(self, draw: ImageDraw.ImageDraw, x: float, y: float, text: str,
                   font: ImageFont.FreeTypeFont, fill: str) -> None:
        """Text with an 8-direction foreground halo so it reads over any map."""
        halo = self._palette["foreground"]
        o = max(1, self._px(1))
        for dx in (-o, 0, o):
            for dy in (-o, 0, o):
                if dx or dy:
                    self._draw_text(draw, x + dx, y + dy, text, font, fill=halo)
        self._draw_text(draw, x, y, text, font, fill=fill)

    # --- scale -------------------------------------------------------------
    def _calculate_scale(self, plate_w: int, plate_h: int) -> float:
        """Metres per pixel for the plate, from bounds and plate dimensions."""
        metres_per_degree_lat = 111_320
        centre_lat = (self._min_lat + self._max_lat) / 2
        metres_per_degree_lon = metres_per_degree_lat * math.cos(math.radians(centre_lat))
        lat_range_m = (self._max_lat - self._min_lat) * metres_per_degree_lat
        lon_range_m = (self._max_lon - self._min_lon) * metres_per_degree_lon
        return max(lat_range_m / plate_h, lon_range_m / plate_w)


def get_config_schema() -> ConfigSchema:
    """Return the config schema for this plugin."""
    return ConfigSchema(
        plugin_name="map_screen",
        plugin_type="screen",
        fields=[
            ConfigField(
                key="update_interval",
                label="Min Update Interval",
                field_type=ConfigFieldType.FLOAT,
                default=300.0,
            ),
            ConfigField(
                key="bounds",
                label="Map Bounds",
                field_type=ConfigFieldType.BBOX,
                default=None,
                required=False,
                description="Geographic bounding box for the map. Requires a Mapbox API key and an active renderer.",
            ),
            ConfigField(
                key="map_style",
                label="Map Style",
                field_type=ConfigFieldType.STRING,
                default="mapbox/light-v11",
                description="Mapbox style for the map tiles. Choose a style matching the panel's colour capability (e.g. Spectra 6 / Gallery 7 / Black & White).",
            ),
        ],
    )


def make_plugin(**kwargs: Any) -> ScreenPlugin:
    """Factory function for plugin system."""
    return MapScreen(**kwargs)
