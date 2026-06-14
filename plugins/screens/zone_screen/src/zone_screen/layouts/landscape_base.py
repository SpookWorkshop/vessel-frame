"""Shared base for the landscape zone layouts.

Holds the plan-view hull rendering and info-line helpers used across the
landscape compact/standard layouts (and the info line in large). Each concrete
landscape layout is self-sizing from its own design width.
"""
from __future__ import annotations

from vf_core.marine_utils import mmsi_country

from .base import ZoneLayout


class LandscapeLayout(ZoneLayout):
    """Common landscape helpers (hull orientation/drawing + spec info line)."""

    # Long hulls (tankers/cargo, >= 5:1) look better drawn vertically. Chunkier
    # working boats (fishing/tug/ferry) look better horizontally.
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
        parts = [p for p in (country, f"{v_len}m x {v_wid}m",
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
