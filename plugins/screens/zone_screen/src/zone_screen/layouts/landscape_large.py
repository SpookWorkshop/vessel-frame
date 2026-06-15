"""Landscape large layout for the 13" panel (1600x1200).

The hull is drawn at its true heading inside a compass rose, with four data
sections (motion / voyage / dimensions / position) along the foot. Self-sizing
from a 1600px design width.
"""
from __future__ import annotations

import datetime
import math

from PIL import ImageDraw
from vf_core.marine_utils import compass, fmt_lat, fmt_lon, nav_status_label, range_bearing
from vf_core.text_utils import FONT_FLOOR

from .landscape_base import LandscapeLayout


class LandscapeLarge(LandscapeLayout):
    """Large landscape "chart plate" layout (13")."""

    def _ls_compass_rose(self, draw, cx, cy, R, f_card, px):
        line = self._palette["line"]
        thin = max(1, px(1))
        thick = max(2, px(2))
        off = self._heading_offset
        draw.ellipse([cx - R, cy - R, cx + R, cy + R], outline=line, width=thin)
        for b in range(0, 360, 15):
            major = (b % 90 == 0)
            tl = px(20) if major else px(10)
            a = math.radians(b + off)
            sin_a, cos_a = math.sin(a), math.cos(a)
            draw.line([(cx + (R - tl) * sin_a, cy - (R - tl) * cos_a),
                       (cx + R * sin_a, cy - R * cos_a)], line, thick if major else thin)
        g = px(30)
        for letter, bearing in (("N", 0), ("E", 90), ("S", 180), ("W", 270)):
            a = math.radians(bearing + off)
            draw.text((cx + (R + g) * math.sin(a), cy - (R + g) * math.cos(a)),
                      letter, font=f_card, fill=line, anchor="mm")

    def _ls_heading_ship(self, draw, cx, cy, R, vessel, px):
        line = self._palette["line"]
        ship_len = vessel.get("stern", 0) + vessel.get("bow", 0)
        ship_wid = vessel.get("port", 0) + vessel.get("starboard", 0)
        if ship_len == 0 or ship_wid == 0:
            return
        heading = vessel.get("heading", 511)
        hdg = (heading if heading != 511 else vessel.get("course", 0)) + self._heading_offset
        L = R * 1.6                       # hull length ~ 80% of the rose radius each way
        scale = L / ship_len
        half_len, half_wid = L / 2, ship_wid * scale / 2
        nose = min(0.6 * ship_wid * scale, 0.15 * L)
        a = math.radians(hdg)
        fx, fy = math.sin(a), -math.cos(a)     # bow (forward) direction
        sx, sy = math.cos(a), math.sin(a)      # starboard direction
        def m(av, bv):
            return (cx + av * fx + bv * sx, cy + av * fy + bv * sy)
        pts = [m(-half_len, -half_wid), m(half_len - nose, -half_wid), m(half_len, 0),
               m(half_len - nose, half_wid), m(-half_len, half_wid)]
        draw.polygon(pts, outline=line, width=max(1, px(3)))
        dx, dy = m(-half_len + vessel.get("stern", 0) * scale, -half_wid + vessel.get("port", 0) * scale)
        r = max(2, px(8))
        draw.ellipse([dx - r, dy - r, dx + r, dy + r], fill=self._palette["accent"])

        # heading marker: a small filled caret on the rim where the bow aims
        tip = (cx + (R + px(16)) * fx, cy + (R + px(16)) * fy)
        base = (cx + R * fx, cy + R * fy)
        w = px(9)
        draw.polygon([tip, (base[0] + w * sx, base[1] + w * sy),
                      (base[0] - w * sx, base[1] - w * sy)], fill=line)

    def _ls_sections(self, vessel, px):
        v_len = vessel.get("stern", 0) + vessel.get("bow", 0)
        v_wid = vessel.get("port", 0) + vessel.get("starboard", 0)
        v_dr = vessel.get("draught", 0)
        speed, course = vessel.get("speed", 0), vessel.get("course", 0)
        heading = vessel.get("heading", 511)
        lat, lon = vessel.get("lat"), vessel.get("lon")
        dest = (vessel.get("destination") or "").strip().upper() or f"{self._zone_name} waters".upper()
        eta = vessel.get("eta")
        status = nav_status_label(vessel.get("status"))
        rot = vessel.get("rate_of_turn")
        if lat is not None and lon is not None:
            rng, brg = range_bearing(self._zone_lat, self._zone_lon, lat, lon)
            rng_s, brg_s = f"{rng:.1f} nm", f"{round(brg)}° {compass(brg)}"
        else:
            rng_s = brg_s = "-"
        # 4-row sections (MOTION, POSITION) bookend the 3-row ones for balance.
        return {
            "MOTION": [("Speed", f"{speed:g} kn"), ("Course", f"{course:g}° {compass(course)}"),
                       ("Heading", f"{int(round(heading))}°" if heading != 511 else "-"),
                       ("Rate of turn", f"{rot:g}°/min" if rot is not None else "-")],
            "VOYAGE": [("Bound for", dest), ("ETA", eta or "-"), ("Status", status.upper() if status else "-")],
            "DIMENSIONS": [("Length", f"{v_len} m"), ("Beam", f"{v_wid} m"), ("Draught", f"{v_dr:g} m")],
            "POSITION": [("Latitude", fmt_lat(lat) if lat is not None else "-"),
                         ("Longitude", fmt_lon(lon) if lon is not None else "-"),
                         ("Range", rng_s), ("Bearing", brg_s)],
        }

    def _ls_draw_section(self, draw, cx, top, w, title, rows, fonts, px):
        f_seclabel, f_rlabel, f_rval = fonts
        line = self._palette["line"]
        cr = round(cx + w - px(30))
        self._draw_text(draw, cx, top, title, f_seclabel)
        ry = top + self._line_height(f_seclabel) + px(6)
        draw.line([(cx, ry), (cr, ry)], line, max(2, px(2)))
        ry += px(16)
        row_h = self._line_height(f_rval) + px(11)
        for lab, val in rows:
            _, bl, _ = self._draw_text(draw, cx, ry, lab, f_rlabel)
            self._draw_text(draw, cr, ry, val, f_rval, halign="right", baseline_y=bl)
            ry += row_h

    async def render(self):
        vessel = self._current_vessel
        canvas = self._renderer.canvas
        draw = ImageDraw.Draw(canvas)
        W, H = canvas.size
        self._renderer.clear()
        if vessel is None:
            await self._renderer.flush()
            return

        s = W / 1600
        def px(v):
            return max(1, round(v * s))
        am = self._asset_manager
        line = self._palette["line"]
        now = datetime.datetime.now()

        f_brand = am.get_font("secondary", "SemiBold", px(22))
        f_light = am.get_font("secondary", "Regular", px(16))
        f_sub = am.get_font("primary", "400", px(28), True)
        f_info = am.get_font("secondary", "Regular", px(20))
        f_seclabel = am.get_font("secondary", "SemiBold", px(15))
        f_rlabel = am.get_font("secondary", "Regular", px(16))
        f_rval = am.get_font("secondary", "SemiBold", px(19))
        f_card = am.get_font("secondary", "SemiBold", px(24))

        pad = px(64)
        x0, x1 = pad, W - pad
        thin = max(1, px(1))
        thick = max(2, px(2))

        # masthead
        y = pad
        self._draw_text(draw, x0, y, "VESSEL FRAME", f_brand)
        self._draw_text(draw, (x0 + x1) // 2, y, "No. 0183", f_light, halign="centre")
        self._draw_text(draw, x1, y, now.strftime("%d %b %Y · %H:%M"), f_light, halign="right")
        y += self._line_height(f_brand) + px(12)
        draw.line([(x0, y), (x1, y)], line, thin)
        y += px(28)

        # headline: subtitle / name / (flag, dims, draught + identity)
        vtype = (vessel.get("ship_type_name") or "vessel").split(" - ", 1)[0].lower()
        vtype = vtype if vtype not in ("", "unknown", "reserved", "other") else "vessel"
        self._draw_text(draw, x0, y, f"A {vtype} passed at {now.strftime('%H:%M')}", f_sub)
        y += self._line_height(f_sub) + px(8)
        name = vessel.get("name", "")
        f_name = self._fit_font("primary", "700", name, x1 - x0, max(FONT_FLOOR, px(96)), max(FONT_FLOOR, px(48)))
        self._draw_text(draw, x0, y - self._ink_top(f_name, name), name, f_name)
        y += (self._ink_bottom(f_name, "Mg") - self._ink_top(f_name, "Mg")) + px(14)
        self._draw_text(draw, x0, y, self._ls_info_line(vessel), f_info)
        ident = (f"MMSI {vessel.get('identifier', '')}   ·   IMO {vessel.get('imo') or '-'}"
                 f"   ·   Call sign {(vessel.get('callsign') or '-').strip()}")
        self._draw_text(draw, x1, y, ident, f_info, halign="right")
        y += self._line_height(f_info) + px(20)
        draw.line([(x0, y), (x1, y)], line, thin)
        headline_rule_y = y

        # data sections at the base
        secs = self._ls_sections(vessel, px)
        sec_fonts = (f_seclabel, f_rlabel, f_rval)
        sec_header_h = self._line_height(f_seclabel) + px(6) + thick + px(16)
        row_h = self._line_height(f_rval) + px(11)
        cols_h = sec_header_h + max(len(r) for r in secs.values()) * row_h
        cols_top = H - pad - cols_h
        col_w = (x1 - x0) / 4
        for i, (title, rows) in enumerate(secs.items()):
            self._ls_draw_section(draw, round(x0 + i * col_w), cols_top, col_w, title, rows, sec_fonts, px)

        # hero: hull at true heading, inside a compass rose
        hero_top = headline_rule_y + px(24)
        hero_bot = cols_top - px(36)
        ccx, ccy = (x0 + x1) // 2, (hero_top + hero_bot) // 2
        R = max(px(120), min((hero_bot - hero_top) // 2 - px(46), px(440)))
        self._ls_compass_rose(draw, ccx, ccy, R, f_card, px)
        self._ls_heading_ship(draw, ccx, ccy, R, vessel, px)

        await self._renderer.flush()
