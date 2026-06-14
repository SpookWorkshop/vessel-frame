"""Base class for table-screen layouts.

Holds the render context, the per-panel scale machinery (every tier scales from a
per-profile reference width — there's no iterative fit-guard) and the shared
vessel-formatting / recency / masthead / legend / stat / outline helpers that
keep the tiers consistent. Concrete layouts implement render(vessels, total).
"""
from __future__ import annotations

import datetime
from typing import Any

from PIL import ImageDraw, ImageFont

from vf_core.marine_utils import nav_status_short
from vf_core.text_utils import TextRenderingMixin

# Design reference widths per profile (the panel's long edge), per orientation;
# fonts/spacing scale from these so each launch resolution renders at scale 1.0.
REF_WIDTH = {"compact": 400, "standard": 480, "large": 1200}
REF_WIDTH_LANDSCAPE = {"compact": 600, "standard": 800, "large": 1600}

ISSUE_NO = "No. 0183"

# Recency thresholds (seconds): live (filled square) under LIVE_MAX,
# recent (empty square) under RECENT_MAX, older (dot) beyond that.
LIVE_MAX = 60
RECENT_MAX = 300


class TableLayout(TextRenderingMixin):
    """Render context, scale machinery + shared table helpers.

    TextRenderingMixin requires ``self._palette`` and ``self._asset_manager``,
    both set here, so subclasses use the drawing/font helpers directly.
    """

    def __init__(
        self,
        *,
        renderer: Any,
        asset_manager: Any,
        profile: str,
        orientation: str,
    ) -> None:
        self._renderer = renderer
        self._asset_manager = asset_manager
        self._palette = renderer.palette
        self._profile = profile
        self._orientation = orientation

        canvas_w, _ = renderer.canvas.size
        refs = REF_WIDTH_LANDSCAPE if orientation == "landscape" else REF_WIDTH
        self._scale = canvas_w / refs[profile]
        self._line_w = max(1, round(2 * self._scale))
        self._gap = max(1, round(16 * self._scale))
        self._gap_s = max(1, round(5 * self._scale))

    async def render(self, vessels: list[dict], total: int) -> None:
        """Draw the vessel table to the canvas."""
        raise NotImplementedError

    def _px(self, v: float) -> int:
        return max(1, round(v * self._scale))

    # --- vessel formatting -------------------------------------------------
    def _vessel_name(self, vessel: dict) -> str:
        """Display name, falling back to the mmsi then 'Unknown'."""
        name = vessel.get("name")
        if not name or name == "Unknown":
            name = vessel.get("identifier") or "Unknown"
        return name

    def _vessel_type(self, vessel: dict) -> str:
        """Main ship type, lowercased. 'vessel' when unknown/reserved."""
        raw = (vessel.get("ship_type_name") or "").split(" - ", 1)[0].strip().lower()
        return raw if raw not in ("", "unknown", "reserved", "other") else "vessel"

    def _vessel_status(self, vessel: dict) -> str:
        """Short nav-status word. Derive 'under way' from speed if status absent."""
        text = nav_status_short(vessel.get("status"))
        if text:
            return text
        return "under way" if vessel.get("speed", 0) > 0.5 else ""

    def _vessel_length(self, vessel: dict) -> int:
        return vessel.get("bow", 0) + vessel.get("stern", 0)

    def _vessel_beam(self, vessel: dict) -> int:
        return vessel.get("port", 0) + vessel.get("starboard", 0)

    def _age_text(self, now: float, ts: float) -> str:
        """Compact 'time since last heard': now / 22s / 5m / 2h."""
        a = int(now - ts)
        if a < 0:
            a = 0
        if a < LIVE_MAX:
            return "now" if a < 5 else f"{a}s"
        if a < 3600:
            return f"{a // 60}m"
        return f"{a // 3600}h"

    def _recency(self, now: float, ts: float) -> str:
        """'live' | 'recent' | 'old' bucket for the row glyph."""
        a = now - ts
        if a < LIVE_MAX:
            return "live"
        return "recent" if a < RECENT_MAX else "old"

    # --- drawing helpers ---------------------------------------------------
    def _truncate(self, font: ImageFont.FreeTypeFont, text: str, max_w: int) -> str:
        """Trim with a trailing ellipsis so the text fits within max_w px."""
        if self._text_width(font, text) <= max_w:
            return text
        ell = "…"
        for i in range(len(text) - 1, 0, -1):
            candidate = text[:i].rstrip() + ell
            if self._text_width(font, candidate) <= max_w:
                return candidate
        return ell

    def _draw_glyph(self, draw: ImageDraw.ImageDraw, x_left: int, cy: int,
                    kind: str, size: int) -> None:
        """Recency marker: filled square (live), empty square (recent), dot (old)."""
        accent = self._palette["accent"]
        top = cy - size // 2
        if kind == "live":
            draw.rectangle([x_left, top, x_left + size, top + size], fill=accent)
        elif kind == "recent":
            draw.rectangle([x_left, top, x_left + size, top + size],
                           outline=accent, width=self._line_w)
        else:
            r = max(1, self._line_w + 1)
            cx = x_left + size // 2
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=self._palette["text"])

    def _draw_masthead(self, draw: ImageDraw.ImageDraw, x0: int, x1: int, y: int,
                       brand_f: ImageFont.FreeTypeFont, meta_f: ImageFont.FreeTypeFont,
                       stacked_date: bool) -> int:
        """Brand / issue no. / date masthead. Returns y at the bottom of the block.

        stacked_date: True draws time over date on two right-aligned lines (large
        tier). False draws a single 'dd Mon HH:MM' line (compact/standard).
        """
        now = datetime.datetime.now()
        self._draw_text(draw, x0, y, "VESSEL FRAME", brand_f)
        self._draw_text(draw, (x0 + x1) // 2, y, ISSUE_NO, meta_f, halign="centre")
        if stacked_date:
            self._draw_text(draw, x1, y, now.strftime("%H:%M"), meta_f, halign="right")
            self._draw_text(draw, x1, y + self._line_height(meta_f), now.strftime("%d %b %Y"),
                       meta_f, halign="right")
            return y + max(self._line_height(brand_f), 2 * self._line_height(meta_f))
        self._draw_text(draw, x1, y, now.strftime("%d %b  %H:%M"), meta_f, halign="right")
        return y + self._line_height(brand_f)

    def _draw_legend(self, draw: ImageDraw.ImageDraw, x0: int, y: int,
                     legend_f: ImageFont.FreeTypeFont, glyph: int,
                     short: bool = False) -> None:
        """Recency legend: Filled square <1 min, empty square 1-5 min, dot if older (left-aligned)."""
        P = self._palette
        gap = self._gap
        cy = y + self._line_height(legend_f) // 2
        labels = ("<1m", "1-5m", "older") if short else ("<1 min", "1-5 min", "older")
        lx = x0
        top = cy - glyph // 2
        draw.rectangle([lx, top, lx + glyph, top + glyph], fill=P["accent"])
        lx += glyph + self._gap_s
        _, _, w = self._draw_text(draw, lx, y, labels[0], legend_f)
        lx += w + gap
        draw.rectangle([lx, top, lx + glyph, top + glyph], outline=P["accent"], width=self._line_w)
        lx += glyph + self._gap_s
        _, _, w = self._draw_text(draw, lx, y, labels[1], legend_f)
        lx += w + gap
        r = max(1, self._line_w + 1)
        cx = lx + glyph // 2
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=P["text"])
        lx += glyph + self._gap_s
        self._draw_text(draw, lx, y, labels[2], legend_f)

    def _stat(self, draw: ImageDraw.ImageDraw, x: int, y: int, label: str, num: str,
              unit: str, subval: str | None, fonts: tuple) -> None:
        """One stats-bar cell: small-caps label, big number (+ unit), optional subval."""
        f_lbl, f_num, f_unit, f_sub = fonts
        self._draw_text(draw, x, y, label, f_lbl)
        ny = y + self._line_height(f_lbl) + self._px(6)
        _, bl, nw = self._draw_text(draw, x, ny, num, f_num)
        if unit:
            self._draw_text(draw, x + nw + self._px(5), ny, unit, f_unit, baseline_y=bl)
        if subval:
            self._draw_text(draw, x, bl + self._px(8), subval, f_sub)

    def _outline(self, draw: ImageDraw.ImageDraw, x_left: int, cy: int, length_m: float,
                 beam_m: float, scale: float, max_beam_px: float) -> None:
        """Horizontal vessel silhouette (bow right), scaled by scale (px/m),
        left-aligned so all sterns share a baseline for easy length comparison."""
        if length_m <= 0 or beam_m <= 0:
            return
        L = length_m * scale
        B = min(beam_m * scale, max_beam_px)
        nose = min(0.5 * B, 0.18 * L)
        pts = [
            (x_left, cy - B / 2), (x_left + L - nose, cy - B / 2), (x_left + L, cy),
            (x_left + L - nose, cy + B / 2), (x_left, cy + B / 2),
        ]
        draw.polygon(pts, outline=self._palette["line"], width=self._line_w)
