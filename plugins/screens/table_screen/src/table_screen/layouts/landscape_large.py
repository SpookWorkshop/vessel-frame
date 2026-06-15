"""Landscape large layout for the 13" panel.

A top band (masthead, hero count + editorial stats) over two rich columns, each
with a to-scale outline.
"""
from __future__ import annotations

import time

from PIL import ImageDraw
from vf_core.marine_utils import compass

from .landscape_base import LandscapeTableLayout


class LandscapeLarge(LandscapeTableLayout):
    """Two-column broadsheet layout for large landscape panels (13")."""

    async def render(self, vessels: list[dict], total: int) -> None:
        canvas = self._renderer.canvas
        draw = ImageDraw.Draw(canvas)
        W, H = canvas.size
        px = self._px
        P = self._palette
        line = P["line"]
        am = self._asset_manager
        now = time.time()

        self._renderer.clear()

        f_brand = am.get_font("secondary", "SemiBold", px(20))
        f_meta = am.get_font("secondary", "Regular", px(14))
        f_eyebrow = am.get_font("secondary", "SemiBold", px(15))
        f_hero = am.get_font("primary", "700", px(58))
        f_slabel = am.get_font("secondary", "SemiBold", px(12))
        f_snum = am.get_font("secondary", "SemiBold", px(42))
        f_sunit = am.get_font("secondary", "Regular", px(16))
        f_ssub = am.get_font("primary", "400", px(15), True)
        f_colhead = am.get_font("secondary", "Regular", px(13))
        f_name = am.get_font("primary", "700", px(24))
        f_sub = am.get_font("primary", "400", px(14), True)
        f_cell = am.get_font("secondary", "Regular", px(15))
        f_speed = am.get_font("secondary", "SemiBold", px(17))
        f_sp_unit = am.get_font("secondary", "Regular", px(11))
        f_legend = am.get_font("secondary", "Regular", px(13))

        margin = px(40)
        x0, x1 = margin, W - margin
        cw = x1 - x0
        thick = px(2)

        # --- top band: masthead, hero (left) + stats (right) ---
        y = self._draw_masthead(draw, x0, x1, margin, f_brand, f_meta, stacked_date=True)
        y += px(10)
        draw.line([(x0, y), (x1, y)], line, thick)
        y += px(22)
        self._draw_text(draw, x0, y, "IN RANGE RIGHT NOW", f_eyebrow)
        y += self._line_height(f_eyebrow) + px(10)
        lh, _, _ = self._draw_text(draw, x0, y, f"{total} vessels", f_hero)
        if vessels:
            live = sum(1 for v in vessels if now - v.get("ts", 0) < 60)
            recent = sum(1 for v in vessels if 60 <= now - v.get("ts", 0) < 300)
            underway = sum(1 for v in vessels if v.get("speed", 0) > 0.5)
            longest = max(vessels, key=self._vessel_length)
            sfonts = (f_slabel, f_snum, f_sunit, f_ssub)
            stat_x = x0 + cw // 2
            qcol = (x1 - stat_x) // 4
            sy = y + px(6)
            self._stat(draw, stat_x + 0 * qcol, sy, "LIVE (<1 MIN)", str(live), "", None, sfonts)
            self._stat(draw, stat_x + 1 * qcol, sy, "RECENT (1–5 MIN)", str(recent), "", None, sfonts)
            self._stat(draw, stat_x + 2 * qcol, sy, "UNDER WAY", str(underway), "", None, sfonts)
            self._stat(draw, stat_x + 3 * qcol, sy, "LONGEST", str(self._vessel_length(longest)),
                       "m", self._vessel_name(longest), sfonts)
        y += lh + px(22)
        draw.line([(x0, y), (x1, y)], line, thick)
        band_top = y + px(18)

        # --- two rich columns ---
        col_gap = px(48)
        col_w = (cw - col_gap) // 2
        cols_x = [x0, x0 + col_w + col_gap]
        footer_h = self._line_height(f_legend) + px(14)
        bottom_rule_y = H - margin - footer_h
        draw.line([(x0 + col_w + col_gap // 2, band_top),
                   (x0 + col_w + col_gap // 2, bottom_rule_y - px(8))], line, self._line_w)

        row_pitch = self._line_height(f_name) + self._line_height(f_sub) + px(18)
        head_h = self._line_height(f_colhead) + px(8) + px(14)
        capacity = max(1, (bottom_rule_y - band_top - head_h) // row_pitch)
        chunks, _ = self._balanced_chunks(vessels, capacity)
        max_len = max((self._vessel_length(v) for v in vessels), default=1) or 1
        glyph = px(14)
        cpad = px(8)
        fr = [0.40, 0.24, 0.13, 0.09, 0.14]  # vessel, outline, speed, crs, heard

        shown = 0
        for ci, cx0 in enumerate(cols_x):
            cx1 = cx0 + col_w
            xs = [cx0]
            for fdef in fr:
                xs.append(xs[-1] + int(col_w * fdef))
            name_x = cx0 + glyph + px(16)
            out_x0 = xs[1]
            scale = (xs[2] - xs[1] - px(20)) / max_len
            speed_right = xs[3] - cpad
            crs_x = xs[3] + cpad
            name_max = out_x0 - px(12) - name_x

            yh = band_top
            self._draw_text(draw, name_x, yh, "VESSEL", f_colhead)
            self._draw_text(draw, xs[1] + cpad, yh, "OUTLINE", f_colhead)
            self._draw_text(draw, speed_right, yh, "SPEED", f_colhead, halign="right")
            self._draw_text(draw, crs_x, yh, "CRS", f_colhead)
            self._draw_text(draw, cx1, yh, "HEARD", f_colhead, halign="right")
            yh += self._line_height(f_colhead) + px(8)
            draw.line([(cx0, yh), (cx1, yh)], line, thick)
            y = yh + px(14)

            for v in chunks[ci]:
                if y + row_pitch > bottom_rule_y:
                    break
                name = self._truncate(f_name, self._vessel_name(v), name_max)
                name_lh, name_bl, _ = self._draw_text(draw, name_x, y, name, f_name)
                cy = (y + self._ink_top(f_name, "M") + y + self._ink_bottom(f_name, "M")) // 2
                self._draw_glyph(draw, cx0, cy, self._recency(now, v.get("ts", 0)), glyph)
                self._outline(draw, out_x0, cy, self._vessel_length(v), self._vessel_beam(v),
                              scale, max_beam_px=self._line_height(f_name) * 0.85)
                sp = v.get("speed", 0)
                if sp > 0:
                    kn_w = self._text_width(f_sp_unit, "kn")
                    self._draw_text(draw, speed_right, y, "kn", f_sp_unit, halign="right", baseline_y=name_bl)
                    self._draw_text(draw, speed_right - kn_w - px(3), y, f"{sp:g}", f_speed,
                                    halign="right", baseline_y=name_bl)
                    crs = compass(v.get("course", 0))
                else:
                    self._draw_text(draw, speed_right, y, "-", f_speed, halign="right", baseline_y=name_bl)
                    crs = "-"
                self._draw_text(draw, crs_x, y, crs, f_cell, baseline_y=name_bl)
                self._draw_text(draw, cx1, y, self._age_text(now, v.get("ts", 0)), f_cell,
                                halign="right", baseline_y=name_bl)
                parts = [p for p in (self._vessel_type(v), self._vessel_status(v)) if p]
                self._draw_text(draw, name_x, y + int(name_lh * 0.86), "  ·  ".join(parts), f_sub)
                y += row_pitch
                shown += 1

        draw.line([(x0, bottom_rule_y), (x1, bottom_rule_y)], line, thick)
        fy = bottom_rule_y + px(8)
        self._draw_legend(draw, x0, fy, f_legend, px(11))
        self._draw_text(draw, x1, fy, f"{shown} of {total} shown", f_legend, halign="right")

        await self._renderer.flush()
