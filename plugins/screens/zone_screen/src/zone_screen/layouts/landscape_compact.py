"""Landscape compact layout for the 4" panel (600x400).

Headline + identity on the left, a plan-view hull on the right, with a 3-stat
footer (MMSI / SPD / CRS). Self-sizing from a 600px design width.
"""
from __future__ import annotations

import datetime
from PIL import ImageDraw

from vf_core.text_utils import split_two, FONT_FLOOR

from .landscape_base import LandscapeLayout


class LandscapeCompact(LandscapeLayout):
    """Compact landscape layout (4")."""

    async def render(self):
        vessel = self._current_vessel
        canvas = self._renderer.canvas
        draw = ImageDraw.Draw(canvas)
        W, H = canvas.size
        self._renderer.clear()
        if vessel is None:
            await self._renderer.flush()
            return

        orient = self._ls_ship_orient(vessel)
        s = W / 600
        def px(v):
            return max(1, round(v * s))
        am = self._asset_manager
        line = self._palette["line"]
        now = datetime.datetime.now()

        f_brand = am.get_font("secondary", "SemiBold", px(15))
        f_light = am.get_font("secondary", "Regular", px(12))
        f_sub = am.get_font("primary", "400", px(15), True)
        f_info = am.get_font("secondary", "Regular", px(13))
        f_flabel = am.get_font("secondary", "SemiBold", px(11))
        f_fval = am.get_font("primary", "700", px(22))
        f_funit = am.get_font("secondary", "Regular", px(12))

        pad = px(22)
        x0, x1 = pad, W - pad
        thin = max(1, px(1))

        def fit_val(val, avail, mx, mn):
            f = self._fit_font("primary", "700", val, avail, mx, mn)
            def vw(t):
                return f.getbbox(t)[2] - f.getbbox(t)[0]
            if vw(val) <= avail:
                return f, val
            while val and vw(val + "…") > avail:
                val = val[:-1]
            return f, (val + "…" if val else "")

        # header
        y = pad
        self._draw_text(draw, x0, y, "VESSEL FRAME", f_brand)
        self._draw_text(draw, (x0 + x1) // 2, y, "No. 0183", f_light, halign="centre")
        self._draw_text(draw, x1, y, now.strftime("%H:%M"), f_light, halign="right")
        y += self._line_height(f_brand) + px(8)
        draw.line([(x0, y), (x1, y)], line, thin)
        header_rule_y = y

        # footer (bottom): MMSI / SPD / CRS, evenly spread
        flabel_h = self._line_height(f_flabel)
        footer_label_y = H - pad - flabel_h - px(5) - self._line_height(f_fval)
        footer_value_y = footer_label_y + flabel_h + px(5)
        footer_rule_y = footer_label_y - px(12)
        draw.line([(x0, footer_rule_y), (x1, footer_rule_y)], line, thin)
        cols = [
            ("MMSI", vessel.get("identifier", "") or "-", ""),
            ("SPD", f"{vessel.get('speed', 0):g}", "kn"),
            ("CRS", f"{vessel.get('course', 0):g}°", ""),
        ]
        cw = (x1 - x0) / 3
        for i, (lab, val, unit) in enumerate(cols):
            cx = round(x0 + i * cw)
            self._draw_text(draw, cx, footer_label_y, lab, f_flabel)
            uw = (f_funit.getbbox(unit)[2] + px(4)) if unit else 0
            vfont, vtext = fit_val(val, cw - px(10) - uw, px(22), px(12))
            _, bl, vw = self._draw_text(draw, cx, footer_value_y, vtext, vfont)
            if unit:
                self._draw_text(draw, cx + vw + px(3), footer_value_y, unit, f_funit, baseline_y=bl)

        # flag, LxW, draught, sitting just above the footer rule
        info_y = footer_rule_y - px(12) - self._line_height(f_info)
        self._draw_text(draw, x0, info_y, self._ls_info_line(vessel), f_info)

        # body: left = identity, right = diagram
        body_top = header_rule_y + px(20)
        body_bot = info_y - px(14)
        left_w = round((x1 - x0) * 0.54)
        gap = px(26)
        lx0, lx1 = x0, x0 + left_w
        rx0, rx1 = lx1 + gap, x1

        self._ls_draw_ship(draw, (rx0, body_top, rx1, body_bot), vessel, orient, px)

        # left: subtitle / name / destination, vertically centred
        name = vessel.get("name", "")
        vtype = (vessel.get("ship_type_name") or "vessel").split(" - ", 1)[0].lower()
        vtype = vtype if vtype not in ("", "unknown", "reserved", "other") else "vessel"
        sub_text = f"A {vtype} passed at {now.strftime('%H:%M')}"
        raw_dest = (vessel.get("destination") or "").strip()
        dest_text = f"Bound for {raw_dest.title()}" if raw_dest else f"In {self._zone_name} waters".title()

        name_lines = split_two(name) if (len(name) >= 8 and " " in name) else [name]
        widest = max(name_lines, key=len)
        f_name = self._fit_font("primary", "700", widest, left_w, max(FONT_FLOOR, px(54)), max(FONT_FLOOR, px(26)))
        cap = self._ink_bottom(f_name, "M") - self._ink_top(f_name, "M")
        name_adv = cap + px(8)
        name_block = cap + (len(name_lines) - 1) * name_adv
        sub_lh = self._line_height(f_sub)
        f_dest = self._fit_font("primary", "400", dest_text, left_w, px(19), px(13))
        dest_lh = self._line_height(f_dest)
        block_h = sub_lh + px(10) + name_block + px(12) + dest_lh
        top = body_top + max(0, ((body_bot - body_top) - block_h) // 2)

        self._draw_text(draw, lx0, top, sub_text, f_sub)
        ny = top + sub_lh + px(10)
        cursor = ny
        for ln in name_lines:
            self._draw_text(draw, lx0, cursor - self._ink_top(f_name, ln), ln, f_name)
            cursor += name_adv
        dy = ny + name_block + px(12)
        def dw(t):
            return f_dest.getbbox(t)[2] - f_dest.getbbox(t)[0]
        if dw(dest_text) > left_w:
            while dest_text and dw(dest_text + "…") > left_w:
                dest_text = dest_text[:-1]
            dest_text += "…"
        self._draw_text(draw, lx0, dy, dest_text, f_dest)

        await self._renderer.flush()
