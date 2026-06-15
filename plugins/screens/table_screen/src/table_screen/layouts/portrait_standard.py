"""Portrait list layout for the 4" and 7" panels (compact + standard).

Two-line rows (name + type/status), with a speed column added at the standard
tier. Both tiers share this scaled drawing path.
"""
from __future__ import annotations

import time

from PIL import ImageDraw

from .base import TableLayout


class PortraitStandard(TableLayout):
    """Single-column portrait list (compact + standard tiers)."""

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

        margin = px(16) if small else px(22)
        x0, x1 = margin, W - margin
        thick, thin = px(2), self._line_w
        glyph = px(10)
        name_x = x0 + glyph + px(11)

        # masthead + section header (count-first, right-aligned)
        y = self._draw_masthead(draw, x0, x1, margin, f_brand, f_meta, stacked_date=False)
        y += px(7)
        draw.line([(x0, y), (x1, y)], line, thick)
        y += px(12)
        self._draw_text(draw, x1, y, f"{total} VESSELS IN RANGE", f_section, halign="right")
        y += self._line_height(f_section) + px(6)
        draw.line([(x0, y), (x1, y)], line, thin)
        y += px(12)

        # geometry: time at far right, optional speed block to its left
        footer_h = self._line_height(f_legend) + px(10)
        bottom_rule_y = H - margin - footer_h
        tw = self._text_width(f_time, "00m")
        time_right = x1
        if show_speed:
            speed_right = x1 - tw - px(18)
            sw = self._text_width(f_speed, "00.0") + self._text_width(f_sp_unit, "kn") + px(6)
            name_max = speed_right - sw - px(10) - name_x
        else:
            name_max = x1 - tw - px(12) - name_x
        row_pitch = self._line_height(f_name) + self._line_height(f_sub) + px(10)

        shown = 0
        for v in vessels:
            if y + row_pitch > bottom_rule_y:
                break
            name = self._truncate(f_name, self._vessel_name(v), name_max)
            name_lh, name_bl, _ = self._draw_text(draw, name_x, y, name, f_name)
            ink_top = y + self._ink_top(f_name, "M")
            ink_bot = y + self._ink_bottom(f_name, "M")
            self._draw_glyph(draw, x0, (ink_top + ink_bot) // 2,
                             self._recency(now, v.get("ts", 0)), glyph)
            self._draw_text(draw, time_right, y, self._age_text(now, v.get("ts", 0)), f_time,
                       halign="right", baseline_y=name_bl)
            if show_speed:
                speed = v.get("speed", 0)
                if speed > 0:
                    kn_w = self._text_width(f_sp_unit, "kn")
                    self._draw_text(draw, speed_right, y, "kn", f_sp_unit, halign="right", baseline_y=name_bl)
                    self._draw_text(draw, speed_right - kn_w - px(3), y, f"{speed:g}", f_speed,
                               halign="right", baseline_y=name_bl)
                else:
                    self._draw_text(draw, speed_right, y, "-", f_speed, halign="right", baseline_y=name_bl)
            parts = [p for p in (self._vessel_type(v), self._vessel_status(v)) if p]
            self._draw_text(draw, name_x, y + int(name_lh * 0.78), "  ·  ".join(parts), f_sub)
            y += row_pitch
            shown += 1

        # footer: recency legend (left) + shown/total (right)
        draw.line([(x0, bottom_rule_y), (x1, bottom_rule_y)], line, thick)
        fy = bottom_rule_y + px(6)
        self._draw_legend(draw, x0, fy, f_legend, px(8), short=small)
        self._draw_text(draw, x1, fy, f"{shown} of {total} shown", f_legend, halign="right")

        await self._renderer.flush()
