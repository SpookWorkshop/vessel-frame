"""The map screen's single layout: broadsheet frame + map plate + markers.

One design for every resolution and orientation: a masthead band on top, the
map as a bordered plate filling the middle, and a footer band (legend +
attribution). Vessels are heading-oriented hull markers (dot when no heading),
each haloed, with solid/hollow fill for under-way/moored. Names are decluttered.

All colours come from the renderer palette (never hard-coded) so the screen
degrades gracefully across reduced-colour and greyscale panels. Meaning is
expressed by shapes, fill-state and halo, never by just the colour.
"""
from __future__ import annotations

import datetime
import math
import time
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from vf_core.text_utils import TextRenderingMixin

from .bounds import Bounds

ISSUE_NO = "No. 0183"

# Recency buckets (seconds) used to prioritise which labels win a collision.
LIVE_MAX = 60
RECENT_MAX = 300


class MapLayout(TextRenderingMixin):
    """Renders the broadsheet map view. Geometry scales from the canvas size."""

    # Hull pixel clamps. Every vessel draws as a hull, sized to-scale from its
    # dimensions but never below the minimum (so small craft read as a min-size
    # hull rather than switching to a different marker style).
    SHIP_MIN_LENGTH_PX = 14
    SHIP_MAX_LENGTH_PX = 80
    SHIP_MIN_BEAM_PX = 6
    SHIP_MAX_BEAM_PX = 30

    def __init__(self, *, renderer: Any, asset_manager: Any, bounds: Bounds) -> None:
        self._renderer = renderer
        self._asset_manager = asset_manager
        self._palette = renderer.palette
        self._bounds = bounds

        canvas_w, canvas_h = renderer.canvas.size
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

    def _px(self, v: float) -> int:
        return max(1, round(v * self._scale))

    # --- geometry ----------------------------------------------------------
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

    def plate_size(self, canvas_w: int, canvas_h: int) -> tuple[int, int]:
        """Pixel size of the map plate for a given canvas size."""
        x0, y0, x1, y1 = self._layout(canvas_w, canvas_h)["plate"]
        return max(1, x1 - x0), max(1, y1 - y0)

    # --- render ------------------------------------------------------------
    async def render(self, map_image: Image.Image | None, vessels: list[dict]) -> None:
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
        #     hard-clipped to the plate by the paste, so nothing overlaps the
        #     border or draws off the edge. ---
        if map_image is not None:
            plate_img = (map_image.resize((plate_w, plate_h))
                         if map_image.size != (plate_w, plate_h) else map_image.copy())
        else:
            plate_img = Image.new("RGB", (plate_w, plate_h), self._palette["background"])
        pdraw = ImageDraw.Draw(plate_img)

        markers: list[tuple[dict[str, Any], tuple[float, float]]] = []
        if self._bounds.valid:
            mpp = self._bounds.metres_per_pixel(plate_w, plate_h)
            for vessel in vessels:
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
        missing or out of bounds."""
        lat, lon = vessel.get("lat"), vessel.get("lon")
        if lat is None or lon is None:
            return None
        if not self._bounds.contains(lat, lon):
            return None
        return self._bounds.project(lat, lon, plate_w, plate_h)

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
        """Hull (oriented by heading, min-clamped). Dot when heading is unknown."""
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
        minimum. Vessels with no dimensions draw at the minimum hull size."""
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
