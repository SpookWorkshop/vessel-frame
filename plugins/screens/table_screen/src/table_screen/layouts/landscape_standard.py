"""Landscape list layout for the 4" and 7" panels (compact + standard).

A balanced two-column list. The standard size adds a speed column.
"""
from __future__ import annotations

import time

from PIL import ImageDraw

from .landscape_base import LandscapeTableLayout


class LandscapeStandard(LandscapeTableLayout):
    """Two-column landscape list (compact + standard tiers)."""

    async def render(self, vessels: list[dict], total: int) -> None:
        show_speed = self._profile == "standard"
        canvas = self._renderer.canvas
        draw = ImageDraw.Draw(canvas)
        W, H = canvas.size
        px = self._px
        P = self._palette
        line = P["line"]
        am = self._asset_manager
        now = time.time()
        small = self._profile == "compact"

        self._renderer.clear()

        f_brand = am.get_font("secondary", "SemiBold", px(12))
        f_meta = am.get_font("secondary", "Regular", px(10))
        f_section = am.get_font("secondary", "SemiBold", px(12))
        f_name = am.get_font("primary", "700", px(18))
        f_sub = am.get_font("primary", "400", px(11), True)
        f_time = am.get_font("secondary", "Regular", px(11))
        f_speed = am.get_font("secondary", "SemiBold", px(14))
        f_sp_unit = am.get_font("secondary", "Regular", px(9))
        f_legend = am.get_font("secondary", "Regular", px(9) if small else px(10))

        margin = px(16) if small else px(20)
        x0, x1 = margin, W - margin

        # masthead + section header (count-first, right-aligned)
        y = self._draw_masthead(draw, x0, x1, margin, f_brand, f_meta, stacked_date=False)
        y += px(7)
        draw.line([(x0, y), (x1, y)], line, px(2))
        y += px(10)
        self._draw_text(draw, x1, y, f"{total} VESSELS IN RANGE", f_section, halign="right")
        y += self._line_height(f_section) + px(6)
        draw.line([(x0, y), (x1, y)], line, self._line_w)
        y_top = y + px(12)

        footer_h = self._line_height(f_legend) + px(10)
        bottom_rule_y = H - margin - footer_h
        row_pitch = self._line_height(f_name) + self._line_height(f_sub) + px(10)
        capacity = max(1, (bottom_rule_y - y_top) // row_pitch)

        col_gap = px(20) if small else px(28)
        col_w = (x1 - x0 - col_gap) // 2
        cols_x = [x0, x0 + col_w + col_gap]
        draw.line([(x0 + col_w + col_gap // 2, y_top),
                   (x0 + col_w + col_gap // 2, bottom_rule_y - px(6))], line, self._line_w)

        chunks, _ = self._balanced_chunks(vessels, capacity)
        glyph = px(10)
        tw = self._text_width(f_time, "00m")
        shown = 0
        for ci, cx0 in enumerate(cols_x):
            cx1 = cx0 + col_w
            name_x = cx0 + glyph + px(11)
            if show_speed:
                speed_right = cx1 - tw - px(16)
                name_max = speed_right - self._text_width(f_speed, "00.0 kn") - px(10) - name_x
            else:
                speed_right = None
                name_max = cx1 - tw - px(12) - name_x
            y = y_top
            for v in chunks[ci]:
                if y + row_pitch > bottom_rule_y:
                    break
                self._land_row(draw, v, now, name_x, name_max, y, f_name, f_sub, f_time,
                               f_speed, f_sp_unit, cx0, glyph, cx1, speed_right)
                y += row_pitch
                shown += 1

        draw.line([(x0, bottom_rule_y), (x1, bottom_rule_y)], line, px(2))
        fy = bottom_rule_y + px(6)
        self._draw_legend(draw, x0, fy, f_legend, px(8), short=small)
        self._draw_text(draw, x1, fy, f"{shown} of {total} shown", f_legend, halign="right")

        await self._renderer.flush()

    def _land_row(self, draw, v, now, name_x, name_max, y, f_name, f_sub, f_time,
                  f_speed, f_sp_unit, glyph_x, glyph, time_right, speed_right) -> None:
        """One landscape list row: glyph - name - type-status subtitle - [speed] - heard."""
        px = self._px
        name = self._truncate(f_name, self._vessel_name(v), name_max)
        name_lh, name_bl, _ = self._draw_text(draw, name_x, y, name, f_name)
        cy = (y + self._ink_top(f_name, "M") + y + self._ink_bottom(f_name, "M")) // 2
        self._draw_glyph(draw, glyph_x, cy, self._recency(now, v.get("ts", 0)), glyph)
        self._draw_text(draw, time_right, y, self._age_text(now, v.get("ts", 0)), f_time,
                        halign="right", baseline_y=name_bl)
        if speed_right is not None:
            sp = v.get("speed", 0)
            if sp > 0:
                kn_w = self._text_width(f_sp_unit, "kn")
                self._draw_text(draw, speed_right, y, "kn", f_sp_unit, halign="right", baseline_y=name_bl)
                self._draw_text(draw, speed_right - kn_w - px(3), y, f"{sp:g}", f_speed,
                                halign="right", baseline_y=name_bl)
            else:
                self._draw_text(draw, speed_right, y, "-", f_speed, halign="right", baseline_y=name_bl)
        parts = [p for p in (self._vessel_type(v), self._vessel_status(v)) if p]
        self._draw_text(draw, name_x, y + int(name_lh * 0.78), "  ·  ".join(parts), f_sub)
