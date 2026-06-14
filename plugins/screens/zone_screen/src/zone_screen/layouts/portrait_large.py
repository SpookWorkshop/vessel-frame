"""Large-format (1000px+ short side) two-column portrait layout.

A broadsheet-style spread with the vessel diagram and headline on the left and a
data table on the right.
"""
from __future__ import annotations

import datetime
from PIL import ImageDraw

from vf_core.marine_utils import (
    mmsi_country, compass, compass_full, nav_status_label,
    fmt_lat, fmt_lon, range_bearing,
)
from vf_core.text_utils import split_two, FONT_FLOOR

from .base import ZoneLayout

# Reference width this layout was designed at. All px() sizes scale from it.
REF_W = 1200


class PortraitLarge(ZoneLayout):
    """Two-column broadsheet layout for large portrait panels (13")."""

    async def render(self) -> None:
        vessel = self._current_vessel
        canvas = self._renderer.canvas
        draw = ImageDraw.Draw(canvas)
        W, H = canvas.size
        self._renderer.clear()
        if vessel is None:
            await self._renderer.flush()
            return

        s = W / REF_W
        def px(v):
            return max(1, round(v * s))
        am = self._asset_manager
        P = self._palette
        line = P["line"]
        now = datetime.datetime.now()

        f_brand = am.get_font("secondary", "SemiBold", px(20))
        f_small = am.get_font("secondary", "Regular", px(14))
        f_sub = am.get_font("primary", "400", px(24), True)
        f_info = am.get_font("secondary", "Regular", px(18))
        f_sec = am.get_font("secondary", "SemiBold", px(14))
        f_label = am.get_font("secondary", "Regular", px(19))
        f_value = am.get_font("secondary", "SemiBold", px(21))
        f_unit = am.get_font("secondary", "Regular", px(15))
        f_subval = am.get_font("secondary", "Regular", px(14))
        f_dir = am.get_font("secondary", "SemiBold", px(38))
        f_ital = am.get_font("primary", "400", px(18), True)
        f_bignum = am.get_font("secondary", "SemiBold", px(52))
        f_bunit = am.get_font("secondary", "Regular", px(18))
        f_blabel = am.get_font("secondary", "SemiBold", px(12))

        margin = px(44)
        x0, x1 = margin, W - margin
        thick = px(2)
        thin = max(1, px(1))

        country = mmsi_country(vessel.get("identifier", ""))
        v_len = vessel.get("stern", 0) + vessel.get("bow", 0)
        v_wid = vessel.get("port", 0) + vessel.get("starboard", 0)
        v_draught = vessel.get("draught", 0)

        # --- header ---
        y = margin
        self._draw_text(draw, x0, y, "VESSEL FRAME", f_brand)
        self._draw_text(draw, (x0 + x1) // 2, y, "No. 0183", f_small, halign="centre")
        self._draw_text(draw, x1, y, now.strftime("%H:%M"), f_small, halign="right")
        self._draw_text(draw, x1, y + self._line_height(f_small), now.strftime("%d %b %Y"), f_small, halign="right")
        y += max(self._line_height(f_brand), 2 * self._line_height(f_small)) + px(10)
        draw.line([(x0, y), (x1, y)], line, thick)
        y += px(24)

        # --- subtitle ---
        vtype_raw = (vessel.get("ship_type_name") or "").split(" - ", 1)[0].lower()
        vtype = vtype_raw if vtype_raw not in ("", "unknown", "reserved", "other") else "vessel"
        self._draw_text(draw, x0, y, f"A {vtype} passed at {now.strftime('%H:%M')}", f_sub)
        y += self._line_height(f_sub) + px(10)

        # --- title (split long names, reserve two lines. Centre if a single line) ---
        name = vessel.get("name", "")
        lines = split_two(name) if (len(name) >= 10 and " " in name) else [name]
        longest = max(lines, key=len)
        f_title = self._fit_font("primary", "700", longest, x1 - x0, max(FONT_FLOOR, px(100)), max(FONT_FLOOR, px(44)))
        # Tight line advance (cap height + small gap) so two-line names stack
        # closely, freeing vertical room for the columns below.
        cap_h = self._ink_bottom(f_title, "M") - self._ink_top(f_title, "M")
        line_adv = cap_h + px(12)
        title_block = cap_h + line_adv  # reserve two tight lines
        if len(lines) == 1:
            ln = lines[0]
            ink_h = self._ink_bottom(f_title, ln) - self._ink_top(f_title, ln)
            top = y + (title_block - ink_h) // 2 - self._ink_top(f_title, ln)
            self._draw_text(draw, x0, top, ln, f_title)
        else:
            cursor = y
            for ln in lines:
                self._draw_text(draw, x0, cursor - self._ink_top(f_title, ln), ln, f_title)
                cursor += line_adv
        y += title_block + px(12)

        # --- info line ---
        info = [p for p in (country, f"{v_len} m x {v_wid} m",
                            f"{v_draught:g} m draught" if v_draught else "") if p]
        self._draw_text(draw, x0, y, "   •   ".join(info), f_info)
        y += self._line_height(f_info) + px(20)

        # --- full-width rule between title block and body ---
        draw.line([(x0, y), (x1, y)], line, thin)
        y += px(26)
        cols_top = y

        # --- column geometry ---
        gap = px(64)
        left_w = px(440)
        lx0, lx1 = x0, x0 + left_w
        rx0, rx1 = lx1 + gap, x1

        # --- bottom region: stats framed by a diagram-width divider above and a
        #     full-width thin divider below ---
        bottom_rule_y = H - margin - px(34)
        stat_num_lh = self._line_height(f_bignum)
        stat_lbl_lh = self._line_height(f_blabel)
        stats_block_h = stat_lbl_lh + px(6) + stat_num_lh
        stats_top = bottom_rule_y - px(20) - stats_block_h
        diag_rule_y = stats_top - px(18)
        box_bottom = diag_rule_y - px(22)

        draw.line([(lx0, diag_rule_y), (lx1, diag_rule_y)], line, thick)
        draw.line([(x0, bottom_rule_y), (x1, bottom_rule_y)], line, thin)

        stats = [("OVERALL LENGTH", f"{v_len}", "m"),
                 ("BEAM", f"{v_wid}", "m"),
                 ("DRAUGHT", f"{v_draught:g}", "m")]
        sx = lx0
        col_w = (lx1 - lx0) // 3
        for label, num, unit in stats:
            self._draw_text(draw, sx, stats_top, label, f_blabel)
            _, bl, nw = self._draw_text(draw, sx, stats_top + stat_lbl_lh + px(6), num, f_bignum)
            self._draw_text(draw, sx + nw + px(4), stats_top + stat_lbl_lh + px(6), unit, f_bunit, baseline_y=bl)
            sx += col_w

        # --- left column: framed box with vertical ship outline + dot ---
        draw.rectangle([(lx0, cols_top), (lx1, box_bottom)], outline=line, width=thick)
        self._draw_large_diagram(draw, lx0, cols_top, lx1, box_bottom, vessel, px)

        # --- right column data ---
        course = vessel.get("course", 0)
        speed = vessel.get("speed", 0)
        heading = vessel.get("heading", 511)
        dest = (vessel.get("destination") or "").strip()
        lat, lon = vessel.get("lat"), vessel.get("lon")

        heading_str = f"{int(round(heading))}°" if heading != 511 else "-"
        rot = vessel.get("rate_of_turn")
        rot_str, rot_unit = (f"{rot:g}°", "/min") if rot is not None else ("-", "")
        status_num = vessel.get("status")
        status_text = nav_status_label(status_num) or "-"

        # range + bearing measured from the zone centre
        if lat is not None and lon is not None:
            rng, brg = range_bearing(self._zone_lat, self._zone_lon, lat, lon)
            rng_str, rng_unit = f"{rng:.1f}", "nm"
            brg_str, brg_unit = f"{round(brg)}°", compass(brg)
        else:
            rng_str = brg_str = "-"
            rng_unit = brg_unit = ""

        st = vessel.get("ship_type")
        type_sub = f"code {st}" if st else None

        motion = [
            ("Speed over ground", f"{speed:g}", "kn", None, None),
            ("Course over ground", f"{course:g}°", compass(course), None, None),
            ("True heading", heading_str, "", None, None),
            ("Rate of turn", rot_str, rot_unit, None, None),
            ("Navigation status", status_text, "", P["accent"], None),
        ]
        position = [
            ("Latitude", fmt_lat(lat) if lat is not None else "-", "", None, None),
            ("Longitude", fmt_lon(lon) if lon is not None else "-", "", None, None),
            ("Range from zone", rng_str, rng_unit, None, None),
            ("Bearing", brg_str, brg_unit, None, None),
        ]
        identity = [
            ("MMSI", vessel.get("identifier") or "-", "", None, None),
            ("IMO", str(vessel.get("imo") or "-"), "", None, None),
            ("Call sign", (vessel.get("callsign") or "-").strip() or "-", "", None, None),
            ("Ship type", (vessel.get("ship_type_name") or "-").split(" - ", 1)[0], "", None, type_sub),
            ("Flag state", country or "-", "", None, None),
        ]
        data_sections = [("MOTION", motion), ("POSITION", position), ("IDENTITY", identity)]

        # Fill the column: compute a row height that spreads the rows to the
        # bottom dilinevider, so the right side doesn't trail off into whitespace.
        sec_header_h = self._line_height(f_sec) + px(8) + thick + px(18)
        heading_block_h = (sec_header_h + self._line_height(f_sec) + px(8)
                           + self._line_height(f_dir) + px(10) + self._line_height(f_ital) + px(22))
        gs = px(20)
        n_rows = sum(len(r) for _, r in data_sections)
        subval_extra = self._line_height(f_subval) + px(2)
        fixed = heading_block_h + 3 * sec_header_h + 3 * gs + subval_extra
        avail = bottom_rule_y - cols_top
        row_h = (avail - fixed) / n_rows
        row_h = int(max(self._line_height(f_value) + px(16), min(row_h, px(64))))

        def section(yy, title):
            self._draw_text(draw, rx0, yy, title, f_sec)
            yy += self._line_height(f_sec) + px(8)
            draw.line([(rx0, yy), (rx1, yy)], line, thick)
            return yy + px(18)

        def row(yy, label, value, unit, colour, subval, rule=True):
            _, bl, _ = self._draw_text(draw, rx0, yy, label, f_label)
            if unit:
                uw = f_unit.getbbox(unit)[2] - f_unit.getbbox(unit)[0]
                self._draw_text(draw, rx1 - uw - px(5), yy, value, f_value, halign="right",
                           fill=colour or P["text"], baseline_y=bl)
                self._draw_text(draw, rx1, yy, unit, f_unit, halign="right", baseline_y=bl)
            else:
                self._draw_text(draw, rx1, yy, value, f_value, halign="right",
                           fill=colour or P["text"], baseline_y=bl)
            extra = 0
            if subval:
                self._draw_text(draw, rx1, bl + px(4), subval, f_subval, halign="right")
                extra = subval_extra
            yy += row_h + extra
            if rule:
                draw.line([(rx0, yy - px(9)), (rx1, yy - px(9))], line, thin)
            return yy

        ry = cols_top
        # HEADING
        ry = section(ry, "HEADING")
        self._draw_text(draw, rx0, ry, "TRAVELLING", f_sec)
        ry += self._line_height(f_sec) + px(8)
        self._draw_text(draw, rx0, ry, compass_full(course), f_dir)
        ry += self._line_height(f_dir) + px(10)
        dest_phrase = dest.upper() if dest else "no destination reported"
        self._draw_text(draw, rx0, ry, f"Course {course:g}° at {speed:g} kn · {dest_phrase}", f_ital)
        ry += self._line_height(f_ital) + px(22)

        for si, (title, rows) in enumerate(data_sections):
            ry = section(ry, title)
            last_sec = si == len(data_sections) - 1
            for ri, (label, value, unit, colour, subval) in enumerate(rows):
                last_row = last_sec and ri == len(rows) - 1
                ry = row(ry, label, value, unit, colour, subval, rule=not last_row)
            ry += gs

        await self._renderer.flush()

    def _draw_large_diagram(self, draw, x0, y0, x1, y1, vessel, px) -> None:
        """Vertical ship outline (bow up) with a GPS position dot."""
        ship_len = vessel.get("stern", 0) + vessel.get("bow", 0)
        ship_wid = vessel.get("port", 0) + vessel.get("starboard", 0)
        if ship_len == 0 or ship_wid == 0:
            return
        pad = px(28)
        avail_w = (x1 - x0) - 2 * pad
        avail_h = (y1 - y0) - 2 * pad
        # Fit to the box, but cap the beam so stubby vessels don't balloon to
        # fill the whole tall box, they stay boat-shaped and centred.
        max_w = avail_w * 0.55
        scale = min(avail_w / ship_wid, avail_h / ship_len, max_w / ship_wid)
        sl = ship_len * scale
        sw = ship_wid * scale
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2
        half_l, half_w = sl / 2, sw / 2
        nose = min(0.6 * sw, 0.15 * sl)
        lw = max(1, px(2))
        pts = [
            (cx - half_w, cy + half_l),
            (cx - half_w, cy - half_l + nose),
            (cx, cy - half_l),
            (cx + half_w, cy - half_l + nose),
            (cx + half_w, cy + half_l),
        ]
        draw.polygon(pts, outline=self._palette["line"], width=lw)
        dot_y = (cy + half_l) - vessel.get("stern", 0) * scale
        dot_x = (cx - half_w) + vessel.get("port", 0) * scale
        r = max(2, px(7))
        draw.ellipse([dot_x - r, dot_y - r, dot_x + r, dot_y + r], fill=self._palette["accent"])
