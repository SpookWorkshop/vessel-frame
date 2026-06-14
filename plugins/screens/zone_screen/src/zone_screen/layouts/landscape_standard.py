"""Landscape standard layout for the 7" panel (800x480).

Headline across the top, a horizontal hull on the left and a structured data
panel (motion / position / destination) on the right, with a full spec strip at
the foot. Self-sizing from an 800px design width.
"""
from __future__ import annotations

import datetime
from PIL import ImageDraw

from vf_core.marine_utils import compass, fmt_lat, fmt_lon, nav_status_label
from vf_core.text_utils import FONT_FLOOR

from .landscape_base import LandscapeLayout


class LandscapeStandard(LandscapeLayout):
    """Standard landscape layout (7")."""

    async def render(self):
        vessel = self._current_vessel
        canvas = self._renderer.canvas
        draw = ImageDraw.Draw(canvas)
        W, H = canvas.size
        self._renderer.clear()
        if vessel is None:
            await self._renderer.flush()
            return

        s = W / 800
        def px(v):
            return max(1, round(v * s))
        am = self._asset_manager
        line = self._palette["line"]
        now = datetime.datetime.now()

        f_brand = am.get_font("secondary", "SemiBold", px(14))
        f_light = am.get_font("secondary", "Regular", px(13))
        f_sub = am.get_font("primary", "400", px(18), True)
        f_seclabel = am.get_font("secondary", "SemiBold", px(12))
        f_val = am.get_font("primary", "700", px(26))
        f_valunit = am.get_font("secondary", "Regular", px(13))
        f_body = am.get_font("secondary", "Regular", px(14))
        f_strip = am.get_font("secondary", "Regular", px(13))

        pad = px(26)
        x0, x1 = pad, W - pad
        thin = max(1, px(1))

        # header
        y = pad
        self._draw_text(draw, x0, y, "VESSEL FRAME", f_brand)
        self._draw_text(draw, (x0 + x1) // 2, y, "No. 0183", f_light, halign="centre")
        self._draw_text(draw, x1, y, now.strftime("%d %b %Y · %H:%M"), f_light, halign="right")
        y += self._line_height(f_brand) + px(8)
        draw.line([(x0, y), (x1, y)], line, thin)
        y += px(14)

        # subtitle + title
        vtype = (vessel.get("ship_type_name") or "vessel").split(" - ", 1)[0].lower()
        vtype = vtype if vtype not in ("", "unknown", "reserved", "other") else "vessel"
        self._draw_text(draw, x0, y, f"A {vtype} passed at {now.strftime('%H:%M')}", f_sub)
        y += self._line_height(f_sub) + px(6)
        name = vessel.get("name", "")
        f_name = self._fit_font("primary", "700", name, x1 - x0, max(FONT_FLOOR, px(56)), max(FONT_FLOOR, px(30)))
        self._draw_text(draw, x0, y - self._ink_top(f_name, name), name, f_name)
        y += (self._ink_bottom(f_name, "Mg") - self._ink_top(f_name, "Mg")) + px(16)

        # bottom strip: dims, draught, MMSI, IMO, callsign, evenly spread
        strip_rule_y = H - pad - px(30)
        draw.line([(x0, strip_rule_y), (x1, strip_rule_y)], line, thin)
        v_len = vessel.get("stern", 0) + vessel.get("bow", 0)
        v_wid = vessel.get("port", 0) + vessel.get("starboard", 0)
        items = [f"{v_len}m × {v_wid}m", f"{vessel.get('draught', 0):g}m draught",
                 f"MMSI {vessel.get('identifier', '')}",
                 f"IMO {vessel.get('imo') or '-'}",
                 f"Callsign {(vessel.get('callsign') or '-').strip()}"]
        scw = (x1 - x0) / len(items)
        sy = strip_rule_y + px(12)
        for i, it in enumerate(items):
            self._draw_text(draw, round(x0 + (i + 0.5) * scw), sy, it, f_strip, halign="centre")

        # body: left diagram | divider | right data
        body_top = y
        body_bot = strip_rule_y - px(16)
        left_w = round((x1 - x0) * 0.52)
        lx0, lx1 = x0, x0 + left_w
        div_x = lx1 + px(20)
        rx0, rx1 = div_x + px(20), x1
        draw.line([(div_x, body_top), (div_x, body_bot)], line, thin)

        # the 7" hero zone is wide, so a horizontal hull always reads best
        self._ls_draw_ship(draw, (lx0, body_top, lx1, body_bot), vessel, "horizontal", px)

        # right column: movement / position / destination, distributed to fill
        course = vessel.get("course", 0)
        speed = vessel.get("speed", 0)
        heading = vessel.get("heading", 511)
        lat, lon = vessel.get("lat"), vessel.get("lon")
        dest = (vessel.get("destination") or "").strip().upper() or f"{self._zone_name} waters".upper()
        eta = vessel.get("eta")
        status = nav_status_label(vessel.get("status"))
        rw = rx1 - rx0
        f_dest = self._fit_font("primary", "700", dest, rw, max(FONT_FLOOR, px(22)), max(FONT_FLOOR, px(14)))

        def stat(x, yy, label, value, unit="", halign="left"):
            self._draw_text(draw, x, yy, label, f_seclabel, halign=halign)
            yy2 = yy + self._line_height(f_seclabel) + px(5)
            if not unit:
                self._draw_text(draw, x, yy2, value, f_val, halign=halign)
                return
            vw = f_val.getbbox(value)[2] - f_val.getbbox(value)[0]
            uw = f_valunit.getbbox(unit)[2] - f_valunit.getbbox(unit)[0]
            total = vw + px(3) + uw
            vx = x if halign == "left" else (x - total if halign == "right" else x - total // 2)
            _, bl, _ = self._draw_text(draw, vx, yy2, value, f_val)
            self._draw_text(draw, vx + vw + px(3), yy2, unit, f_valunit, baseline_y=bl)

        lbl_h = self._line_height(f_seclabel) + px(5)
        row_h = lbl_h + self._line_height(f_val)
        dest_h = lbl_h + self._line_height(f_dest)
        if status:
            dest_h += px(4) + self._line_height(f_body)
        gap = max(px(14), ((body_bot - body_top) - (2 * row_h + dest_h)) // 2)

        ry = body_top
        stat(rx0, ry, "SPEED", f"{speed:g}", "kn")
        stat(round(rx0 + rw / 2), ry, "COURSE", f"{course:g}°", compass(course), halign="centre")
        stat(rx1, ry, "HEADING", f"{int(round(heading))}°" if heading != 511 else "-", halign="right")
        ry += row_h + gap
        stat(rx0, ry, "LATITUDE", fmt_lat(lat) if lat is not None else "-")
        stat(round(rx0 + rw / 2), ry, "LONGITUDE", fmt_lon(lon) if lon is not None else "-")
        ry += row_h + gap
        _, bl, _ = self._draw_text(draw, rx0, ry, "BOUND FOR", f_seclabel)
        if eta:
            self._draw_text(draw, rx1, ry, f"ETA {eta}", f_body, halign="right", baseline_y=bl)
        ry += lbl_h
        self._draw_text(draw, rx0, ry, dest, f_dest)
        ry += self._line_height(f_dest)
        if status:
            ry += px(4)
            self._draw_text(draw, rx0, ry, status.upper(), f_body, fill=self._palette["accent"])

        await self._renderer.flush()
