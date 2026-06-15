"""Large-format (1000px+ short side) portrait layout for the table screen.

A front-page treatment: masthead, two-line hero count, an editorial stats bar,
and a wide table with a to-scale vessel outline column.
"""
from __future__ import annotations

import time

from PIL import ImageDraw
from vf_core.marine_utils import compass, mmsi_country

from .base import TableLayout

# Column widths as fractions of the content width:
# vessel, outline, type, status, speed, course, heard. TYPE is a touch wider
# than STATUS (and STATUS correspondingly narrower) so wide type labels like
# "high speed craft" keep a clear gap before the status word.
COL_FRACTIONS = [0.34, 0.17, 0.16, 0.12, 0.09, 0.07, 0.05]


class PortraitLarge(TableLayout):
    """Broadsheet table layout for large portrait panels (13")."""

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
        f_name = am.get_font("primary", "700", px(26))
        f_country = am.get_font("primary", "400", px(15), True)
        f_cell = am.get_font("secondary", "Regular", px(16))
        f_speed = am.get_font("secondary", "SemiBold", px(18))
        f_sp_unit = am.get_font("secondary", "Regular", px(12))
        f_legend = am.get_font("secondary", "Regular", px(13))

        margin = px(44)
        x0, x1 = margin, W - margin
        cw = x1 - x0
        thick = px(2)
        cpad = px(8)

        # --- masthead ---
        y = self._draw_masthead(draw, x0, x1, margin, f_brand, f_meta, stacked_date=True)
        y += px(10)
        draw.line([(x0, y), (x1, y)], line, thick)
        y += px(26)

        # --- eyebrow + hero count ---
        self._draw_text(draw, x0, y, "IN RANGE RIGHT NOW", f_eyebrow)
        y += self._line_height(f_eyebrow) + px(12)
        lh, _, _ = self._draw_text(draw, x0, y, f"{total} vessels", f_hero)
        y += lh + px(24)

        # --- stats bar ---
        live = sum(1 for v in vessels if now - v.get("ts", 0) < 60)
        recent = sum(1 for v in vessels if 60 <= now - v.get("ts", 0) < 300)
        underway = sum(1 for v in vessels if v.get("speed", 0) > 0.5)
        longest = max(vessels, key=self._vessel_length) if vessels else None
        sfonts = (f_slabel, f_snum, f_sunit, f_ssub)
        qcol = cw // 4
        self._stat(draw, x0 + 0 * qcol, y, "LIVE (<1 MIN)", str(live), "", None, sfonts)
        self._stat(draw, x0 + 1 * qcol, y, "RECENT (1-5 MIN)", str(recent), "", None, sfonts)
        self._stat(draw, x0 + 2 * qcol, y, "UNDER WAY", str(underway), "", None, sfonts)
        if longest is not None:
            self._stat(draw, x0 + 3 * qcol, y, "LONGEST", str(self._vessel_length(longest)),
                       "m", self._vessel_name(longest), sfonts)
        y += self._line_height(f_slabel) + px(6) + self._line_height(f_snum) + px(8) \
            + self._line_height(f_ssub) + px(22)
        draw.line([(x0, y), (x1, y)], line, thick)
        y += px(20)

        # --- column geometry ---
        xs = [x0]
        for fr in COL_FRACTIONS:
            xs.append(xs[-1] + int(cw * fr))
        col = {
            "vessel": (xs[0], xs[1], "left"), "outline": (xs[1], xs[2], "left"),
            "type": (xs[2], xs[3], "left"), "status": (xs[3], xs[4], "left"),
            "speed": (xs[4], xs[5], "right"), "crs": (xs[5], xs[6], "left"),
            "time": (xs[6], x1, "right"),
        }
        glyph = px(14)
        name_x = xs[0] + glyph + px(16)

        # --- column headers ---
        heads = {"vessel": "VESSEL", "outline": "OUTLINE (TO SCALE)", "type": "TYPE",
                 "status": "STATUS", "speed": "SPEED", "crs": "CRS", "time": "HEARD"}
        for key, (cx0, cx1, align) in col.items():
            if key == "vessel":
                hx = name_x
            elif align == "right":
                hx = cx1 - cpad
            else:
                hx = cx0 + cpad
            self._draw_text(draw, hx, y, heads[key], f_colhead, halign=align)
        y += self._line_height(f_colhead) + px(10)
        draw.line([(x0, y), (x1, y)], line, thick)
        y += px(18)

        # --- to-scale factor: longest vessel fills the outline column ---
        max_len = max((self._vessel_length(v) for v in vessels), default=1) or 1
        out_x0, out_x1, _ = col["outline"]
        scale = (out_x1 - out_x0 - px(30)) / max_len

        # --- footer geometry + fixed-pitch rows ---
        footer_h = self._line_height(f_legend) + px(14)
        bottom_rule_y = H - margin - footer_h
        row_pitch = self._line_height(f_name) + self._line_height(f_country) + px(20)
        name_max = out_x0 - name_x - px(12)

        shown = 0
        for v in vessels:
            if y + row_pitch > bottom_rule_y:
                break
            name = self._truncate(f_name, self._vessel_name(v), name_max)
            name_lh, name_bl, _ = self._draw_text(draw, name_x, y, name, f_name)
            ink_top = y + self._ink_top(f_name, "M")
            ink_bot = y + self._ink_bottom(f_name, "M")
            cy = (ink_top + ink_bot) // 2
            self._draw_glyph(draw, xs[0], cy, self._recency(now, v.get("ts", 0)), glyph)
            self._draw_text(draw, name_x, y + int(name_lh * 0.92),
                       mmsi_country(v.get("identifier", "")) or "", f_country)
            self._outline(draw, out_x0, cy, self._vessel_length(v), self._vessel_beam(v),
                          scale, max_beam_px=self._line_height(f_name) * 0.85)
            self._draw_text(draw, col["type"][0] + cpad, y, self._vessel_type(v), f_cell, baseline_y=name_bl)
            self._draw_text(draw, col["status"][0] + cpad, y, self._vessel_status(v) or "-",
                       f_cell, baseline_y=name_bl)
            speed = v.get("speed", 0)
            sp_right = col["speed"][1] - cpad
            if speed > 0:
                kn_w = self._text_width(f_sp_unit, "kn")
                self._draw_text(draw, sp_right, y, "kn", f_sp_unit, halign="right", baseline_y=name_bl)
                self._draw_text(draw, sp_right - kn_w - px(3), y, f"{speed:g}", f_speed,
                           halign="right", baseline_y=name_bl)
            else:
                self._draw_text(draw, sp_right, y, "-", f_speed, halign="right", baseline_y=name_bl)
            crs = compass(v.get("course", 0)) if speed > 0 else "-"
            self._draw_text(draw, col["crs"][0] + cpad, y, crs, f_cell, baseline_y=name_bl)
            self._draw_text(draw, x1, y, self._age_text(now, v.get("ts", 0)), f_cell,
                       halign="right", baseline_y=name_bl)
            y += row_pitch
            shown += 1

        # --- footer: recency legend (left) + shown/total (right) ---
        draw.line([(x0, bottom_rule_y), (x1, bottom_rule_y)], line, thick)
        fy = bottom_rule_y + px(8)
        self._draw_legend(draw, x0, fy, f_legend, px(11))
        self._draw_text(draw, x1, fy, f"{shown} of {total} shown", f_legend, halign="right")

        await self._renderer.flush()
