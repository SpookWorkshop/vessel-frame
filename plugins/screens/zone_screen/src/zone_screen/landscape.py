"""Landscape-orientation layouts for the zone screen (4" / 7" / 13").

Selected when the canvas is wider than tall. Three profiles mirror the portrait
density tiers: compact (4" 600×400), standard (7" 800×480) and large (13"
1600×1200. The "chart plate" with a hull drawn at its true heading inside a
compass rose). LandscapeLayout is mixed into ZoneScreen and relies on it for
the renderer, asset manager, palette, zone centre, heading_offset, and the
TextRenderingMixin drawing helpers.
"""
from __future__ import annotations
import datetime
import math
from PIL import ImageDraw

from vf_core.marine_utils import mmsi_country, compass, fmt_lat, fmt_lon, range_bearing, nav_status_label
from vf_core.text_utils import split_two, FONT_FLOOR


class LandscapeLayout:
    """Mixin providing the landscape compact / standard / large layouts."""

    # Long hulls (tankers/cargo, >= ~5:1) read better drawn vertically. Chunkier
    # working boats (fishing/tug/ferry) read better horizontally.
    SHIP_VERTICAL_RATIO = 5.0

    def _ls_ship_orient(self, vessel):
        ship_len = vessel.get("stern", 0) + vessel.get("bow", 0)
        ship_wid = vessel.get("port", 0) + vessel.get("starboard", 0)
        if ship_wid == 0:
            return "horizontal"
        return "vertical" if (ship_len / ship_wid) >= self.SHIP_VERTICAL_RATIO else "horizontal"

    def _ls_info_line(self, vessel):
        country = mmsi_country(vessel.get("identifier", ""))
        v_len = vessel.get("stern", 0) + vessel.get("bow", 0)
        v_wid = vessel.get("port", 0) + vessel.get("starboard", 0)
        v_dr = vessel.get("draught", 0)
        parts = [p for p in (country, f"{v_len}m × {v_wid}m",
                             f"{v_dr:g}m draught" if v_dr else "") if p]
        return "   ·   ".join(parts)

    def _ls_draw_ship(self, draw, box, vessel, orient, px):
        """Plan-view hull (horizontal bow-right or vertical bow-up) + position dot."""
        x0, y0, x1, y1 = box
        ship_len = vessel.get("stern", 0) + vessel.get("bow", 0)
        ship_wid = vessel.get("port", 0) + vessel.get("starboard", 0)
        if ship_len == 0 or ship_wid == 0:
            return
        pad = px(10)
        aw = (x1 - x0) - 2 * pad
        ah = (y1 - y0) - 2 * pad
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        stern, port = vessel.get("stern", 0), vessel.get("port", 0)
        lw = max(1, px(2))
        line = self._palette["line"]

        if orient == "horizontal":
            scale = min(aw / ship_len, ah / ship_wid)
            hl, hw = ship_len * scale / 2, ship_wid * scale / 2
            nose = min(0.6 * 2 * hw, 0.15 * 2 * hl)
            pts = [(cx - hl, cy - hw), (cx + hl - nose, cy - hw), (cx + hl, cy),
                   (cx + hl - nose, cy + hw), (cx - hl, cy + hw)]
            dot_x, dot_y = (cx - hl) + stern * scale, (cy - hw) + port * scale
        else:  # vertical, bow up
            scale = min(aw / ship_wid, ah / ship_len)
            hl, hw = ship_len * scale / 2, ship_wid * scale / 2
            nose = min(0.6 * 2 * hw, 0.15 * 2 * hl)
            pts = [(cx - hw, cy + hl), (cx - hw, cy - hl + nose), (cx, cy - hl),
                   (cx + hw, cy - hl + nose), (cx + hw, cy + hl)]
            dot_x, dot_y = (cx - hw) + port * scale, (cy + hl) - stern * scale

        draw.polygon(pts, outline=line, width=lw)
        r = max(2, px(5))
        draw.ellipse([dot_x - r, dot_y - r, dot_x + r, dot_y + r], fill=self._palette["accent"])

    # --- compact (4" 600×400) ----------------------------------------------
    async def _render_ls_compact(self):
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

        # flag, L×W, draught, sitting just above the footer rule
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

    # --- standard (7" 800×480) ---------------------------------------------
    async def _render_ls_standard(self):
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

    # --- large (13" 1600×1200, "chart plate") ------------------------------
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

    async def _render_ls_large(self):
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
