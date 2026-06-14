from __future__ import annotations
import asyncio
import datetime
from typing import Any
from contextlib import suppress
from PIL import ImageDraw, ImageFont
import logging

from vf_core.message_bus import MessageBus
from vf_core.plugin_types import ConfigField, ConfigFieldType, ConfigSchema, ScreenPlugin, RendererPlugin, require_plugin_args
from vf_core.vessel_manager import VesselManager
from vf_core.asset_manager import AssetManager
from vf_core.render_strategies import PeriodicRenderStrategy

from vf_core.marine_utils import (
    mmsi_country, compass, compass_full, nav_status_label,
    fmt_lat, fmt_lon, range_bearing,
)
from vf_core.text_utils import TextRenderingMixin, split_two, FONT_FLOOR
from .large import LargeLayout
from .landscape import LandscapeLayout


# Design reference width. Portrait fonts/spacing scale relative to this.
REF_W = 480

# Layout profile is chosen by the panel's short side (min of width/height, px):
# at/above PROFILE_LARGE_MIN the dense two-column "large" layout is used; below
# PROFILE_COMPACT_MAX the tight single-column "compact" layout; else "standard".
PROFILE_LARGE_MIN = 1000
PROFILE_COMPACT_MAX = 480

# Responsive fit-to-height guard: shrink the scale by SCALE_SHRINK each step (up
# to FIT_MAX_STEPS) until the minimum layout fits the height, never below MIN_SCALE.
FIT_MAX_STEPS = 40
SCALE_SHRINK = 0.95
MIN_SCALE = 0.3

# Compact layout: the diagram takes this fraction of the space it shares with the
# info band, and is never shorter than MIN_DIAGRAM_BASE * scale px.
COMPACT_DIAGRAM_FRACTION = 0.40
MIN_DIAGRAM_BASE = 80

# Base font specs (role, variation, size, italic) tuned for REF_W.
FONT_SPECS = {
    "sec_header":          ("secondary", "Regular",  11, False),
    "sec_header_semibold": ("secondary", "SemiBold", 11, False),
    "sec_body":            ("secondary", "Regular",  13, False),
    "sec_bigheader":       ("secondary", "SemiBold", 24, False),
    "pri_title":           ("primary",   "700",      28, False),
    "pri_subheader":       ("primary",   "400",      18, True),
    "pri_header":          ("primary",   "400",      64, False),
}

# Representative vessel for sizing the layout when no real vessel is available.
_SAMPLE_VESSEL = {
    "lat": 53.5, "lon": -3.1, "destination": "", "status": 0,
    "speed": 22.4, "course": 75, "heading": 74,
}


class ZoneScreen(ScreenPlugin, TextRenderingMixin, LargeLayout, LandscapeLayout):
    """Screen to display detailed information about a vessel in a zone.

    The layout adapts to the renderer's canvas size by selecting one of three
    profiles (compact / standard / large) and scaling fonts and
    spacing to fit, so a single drawing codebase serves every supported display.
    """

    def __init__(
        self,
        *,
        bus: MessageBus,
        renderer: RendererPlugin,
        vm: VesselManager,
        asset_manager: AssetManager,
        in_topic: str = "vessel.zone_entered",
        update_interval: float = 10.0,
        zone_name: str = "Unknown",
        zone: dict | None = None,
        heading_offset: float = 0.0,
        **kwargs: Any,
    ) -> None:
        require_plugin_args(bus=bus, renderer=renderer, vm=vm, asset_manager=asset_manager)
        self._logger = logging.getLogger(__name__)

        self._bus = bus
        self._renderer = renderer
        self._vessel_manager = vm
        self._asset_manager = asset_manager
        self._in_topic = in_topic
        self._task: asyncio.Task[None] | None = None
        self._palette = renderer.palette
        self._current_vessel: dict[str, Any] | None = None
        self._render_strategy = PeriodicRenderStrategy(
            self._render, renderer.MIN_RENDER_INTERVAL + update_interval
        )

        lat = float(zone["lat"]) if zone else 0.0
        lon = float(zone["lon"]) if zone else 0.0
        rad = float(zone["rad"]) if zone else 0.0
        self._zone_name = zone_name
        self._zone_lat = lat
        self._zone_lon = lon
        self._heading_offset = float(heading_offset)
        self._vessel_manager.register_zone(zone_name, lat, lon, rad)

        # Zone attributes must be set first: the responsive fit-guard measures a
        # sample layout (which references the zone name) to pick the scale.
        canvas_w, canvas_h = self._renderer.canvas.size
        self._orientation = "landscape" if canvas_w > canvas_h else "portrait"
        self._profile = self._select_profile(canvas_w, canvas_h)
        self._setup_responsive(canvas_w, canvas_h)

    # --- profile + scaling -------------------------------------------------
    def _select_profile(self, w: int, h: int) -> str:
        """Pick a layout profile from the canvas size.

        Density is chosen from the cross-axis.
        """
        cross = min(w, h)
        if cross >= PROFILE_LARGE_MIN:
            return "large"
        if cross < PROFILE_COMPACT_MAX:
            return "compact"
        return "standard"

    def _build_fonts(self, s: float) -> None:
        am = self._asset_manager
        self._fonts: dict[str, ImageFont.FreeTypeFont] = {}
        for key, (role, var, size, italic) in FONT_SPECS.items():
            px = max(FONT_FLOOR, round(size * s))
            self._fonts[key] = am.get_font(role, var, px, italic)

    def _apply_scale(self, s: float) -> None:
        compact = self._profile == "compact"
        self._scale = s
        self._screen_padding = max(6, round(25 * s))
        # Compact layouts pack tighter and give the diagram more room.
        self._line_spacing = max(3, round((10 if compact else 15) * s))
        # Small gap hugs a value to its label; big gap separates the groups.
        # On compact the small gap is deliberately tight so the three rows read
        # as distinct clusters rather than an evenly-spaced list.
        if compact:
            self._gap_small = max(3, round(10 * s))
            self._gap_big = max(6, round(14 * s))
        else:
            self._gap_small = self._line_spacing
            self._gap_big = round(self._line_spacing * 1.9)
        self._ship_diagram_padding = max(1, round(5 * s))
        self._ship_inner_padding = max(4, round((16 if compact else 30) * s))
        self._mast_size = max(2, round(10 * s))

    def _setup_responsive(self, w: int, h: int) -> None:
        s = w / REF_W
        # Pick the largest scale <= w/REF_W whose minimum layout still fits the
        # available height, so nothing is ever drawn out of bounds.
        for _ in range(FIT_MAX_STEPS):
            self._apply_scale(s)
            self._build_fonts(s)
            if self._min_layout_height() <= h or s <= MIN_SCALE:
                break
            s *= SCALE_SHRINK

    def _min_layout_height(self) -> int:
        """Minimum pixels the whole screen needs at the current fonts."""
        lf = self._fonts
        pad = self._screen_padding
        line_w = max(2, round(3 * self._scale))
        header_h = self._line_height(lf["sec_header_semibold"])
        footer_h = self._line_height(lf["sec_body"]) + 2 * self._line_spacing
        title_min = self._title_min_h()
        diagram_min = max(40, round(70 * self._scale))
        high_min = (self._compact_highlights_height()
                    if self._profile == "compact" else self._highlights_min_h())
        return (2 * pad + header_h + footer_h + title_min + diagram_min
                + high_min + 5 * line_w)

    def _title_min_h(self) -> int:
        lf = self._fonts
        ls = self._line_spacing
        return (ls + self._line_height(lf["pri_subheader"]) + ls
                + self._line_height(lf["pri_header"]) + ls
                + self._line_height(lf["sec_body"]) + ls)

    def _highlights_min_h(self) -> int:
        lf = self._fonts
        line_w = 2
        pos = self._block_h(lf["sec_header_semibold"], lf["sec_bigheader"])
        move = self._block_h(lf["sec_header_semibold"], lf["pri_title"])
        dest = self._block_h(lf["sec_header_semibold"], lf["pri_title"], lf["sec_body"])
        return pos + dest + move + 2 * line_w

    # --- lifecycle ---------------------------------------------------------
    async def activate(self) -> None:
        """Start listening for zone events and enable periodic rendering."""
        if self._task and not self._task.done():
            return

        await self._render_strategy.start()
        self._render_strategy.request_render()
        self._task = asyncio.create_task(self._update_loop())

    async def deactivate(self) -> None:
        """Stop listening and cancel background work."""
        if self._task and not self._task.done():
            await self._render_strategy.stop()

            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _update_loop(self) -> None:
        """Internal loop that receives zone events and requests renders."""
        try:
            async for msg in self._bus.subscribe(self._in_topic):
                vessel = msg.get("vessel")
                self._logger.info("Zone Screen Update")

                if vessel and self._is_valid_vessel(vessel):
                    self._current_vessel = vessel
                    self._render_strategy.request_render()
        except asyncio.CancelledError:
            raise
        except Exception:
            self._logger.exception("Update loop crashed")
            raise

    def _is_valid_vessel(self, vessel: dict[str, Any]) -> bool:
        """Return True if the vessel has MMSI, a valid name and complete dimensions."""
        if not vessel:
            return False

        if not vessel.get("identifier"):
            return False

        name = vessel.get("name")
        if not name or name == "Unknown":
            return False

        length = vessel.get("bow", 0) + vessel.get("stern", 0)
        width = vessel.get("port", 0) + vessel.get("starboard", 0)
        if length == 0 or width == 0:
            return False

        return True

    # --- layout driver -----------------------------------------------------
    async def _render(self) -> None:
        """Render the detail view for the current vessel, or a waiting state."""
        if self._orientation == "landscape":
            if self._profile == "large":
                await self._render_ls_large()
            elif self._profile == "compact":
                await self._render_ls_compact()
            else:
                await self._render_ls_standard()
            return
        if self._profile == "large":
            await self._render_large()
            return

        vessel = self._current_vessel
        canvas = self._renderer.canvas
        draw = ImageDraw.Draw(canvas)
        width, height = canvas.size
        lf = self._fonts

        line_w = max(2, round(3 * self._scale))
        text_colour = self._palette["line"]
        pad = self._screen_padding
        x = pad
        right = width - pad
        y = pad

        self._renderer.clear()

        header_h = self._line_height(lf["sec_header_semibold"])
        self._draw_header(draw, (x, y), (right, y + header_h))
        y += header_h + line_w
        draw.line([(x, y), (right, y)], text_colour, line_w)
        y += line_w

        if vessel is None:
            await self._renderer.flush()
            return

        # Fixed footer reserved at the bottom.
        footer_h = self._line_height(lf["sec_body"]) + 2 * self._line_spacing
        bottom = height - pad
        footer_top = bottom - footer_h

        # Flexible middle: title / diagram / highlights, dividers between each
        # and above the footer (4 lines total below the header line).
        flex_top = y
        flex_space = footer_top - flex_top - 4 * line_w

        if self._profile == "compact":
            # Title takes its natural height; where the panel has room, allow the
            # name to wrap onto a second line (reserving the extra height for it),
            # otherwise it shrinks to fit one line. The diagram and info band
            # split the rest ~40/60 so the diagram stays prominent.
            name = vessel.get("name", "")
            name_wrap = self._compact_can_wrap(name, right - x, flex_space, vessel)
            title_h = self._title_min_h()
            if name_wrap:
                title_h += self._wrap_extra_h()
            shared = flex_space - title_h
            core = self._info_core_height(x, right, vessel)
            info_min = core + 4 * self._gap_small
            min_diag = round(MIN_DIAGRAM_BASE * self._scale)
            diagram_h = round(shared * COMPACT_DIAGRAM_FRACTION)
            diagram_h = max(min_diag, min(diagram_h, shared - info_min))
            high_h = shared - diagram_h
        else:
            name_wrap = False
            w_title, w_diagram, w_high = 210, 140, 320
            sum_w = w_title + w_diagram + w_high
            title_h = round(flex_space * w_title / sum_w)
            diagram_h = round(flex_space * w_diagram / sum_w)
            high_h = flex_space - title_h - diagram_h

        self._draw_title(draw, (x, y), (right, y + title_h), vessel, name_wrap)
        y += title_h + line_w
        draw.line([(x, y), (right, y)], text_colour, line_w)
        y += line_w

        self._draw_vessel_diagram(draw, (x, y), (right, y + diagram_h), vessel)
        y += diagram_h + line_w
        draw.line([(x, y), (right, y)], text_colour, line_w)
        y += line_w

        self._draw_vessel_highlights(draw, (x, y), (right, y + high_h), vessel)
        y += high_h + line_w
        draw.line([(x, y), (right, y)], text_colour, line_w)

        self._draw_vessel_data(draw, (x, footer_top), (right, bottom), vessel)

        await self._renderer.flush()

    def _block_h(self, *fonts: ImageFont.FreeTypeFont) -> int:
        """Pixel height for a vertical stack of single-line text rows.

        Includes self._line_spacing before the first line and after every line.
        Each positional arg is one font (one line).
        """
        h = self._line_spacing
        for font in fonts:
            a, d = font.getmetrics()
            h += a + d + self._line_spacing
        return h

    def _draw_header(self, draw: ImageDraw.ImageDraw, tl, br) -> None:
        """Brand (left), centred lighter issue number, date (right)."""
        x0, x1, y = tl[0], br[0], tl[1]
        text = self._palette["text"]
        brand_f = self._fonts["sec_header_semibold"]
        light_f = self._fonts["sec_header"]

        draw.text((x0, y), "Vessel Frame", fill=text, font=brand_f)
        brand_w = brand_f.getbbox("Vessel Frame")[2]

        date_text = datetime.datetime.now().strftime("%d %b %Y %H:%M")
        date_w = light_f.getbbox(date_text)[2]
        date_x = x1 - date_w
        draw.text((date_x, y), date_text, fill=text, font=light_f)

        # Centred, lighter issue number. Only if it clears the brand and date.
        issue = "No. 0183"
        issue_w = light_f.getbbox(issue)[2]
        issue_x = (x0 + x1) // 2 - issue_w // 2
        gap = self._line_spacing
        if issue_x > x0 + brand_w + gap and issue_x + issue_w < date_x - gap:
            draw.text((issue_x, y), issue, fill=text, font=light_f)

    def _wrap_gap(self) -> int:
        return max(2, round(8 * self._scale))

    def _wrap_extra_h(self) -> int:
        """Extra title height a wrapped (two-line) name needs over a single line.

        A wrapped name is drawn as two tight lines (cap height + a small gap),
        so it only costs a little more than one line, keeping the header
        compact and the diagram/info at full size.
        """
        header = self._fonts["pri_header"]
        cap_h = self._ink_bottom(header, "M") - self._ink_top(header, "M")
        return (2 * cap_h + self._wrap_gap()) - self._line_height(header)

    def _compact_can_wrap(self, name, width, flex_space, vessel) -> bool:
        """True when the name is too wide for one full-size line AND a second
        line still leaves room for the diagram and info band. Only then is
        wrapping worthwhile rather than shrinking onto one line."""
        if " " not in name:
            return False
        header = self._fonts["pri_header"]
        if header.getbbox(name)[2] - header.getbbox(name)[0] <= width:
            return False
        shared = flex_space - (self._title_min_h() + self._wrap_extra_h())
        info_min = self._info_core_height(0, width, vessel) + 4 * self._gap_small
        min_diag = round(MIN_DIAGRAM_BASE * self._scale)
        return shared >= info_min + min_diag

    def _draw_title(self, draw: ImageDraw.ImageDraw, tl, br, vessel, name_wrap: bool = False) -> None:
        """Type line, vessel name, and spread flag/size info.

        ``name_wrap`` (compact only) requests a two-line name; the caller has
        already reserved the extra height for it.
        """
        subheader_font = self._fonts["pri_subheader"]
        body_font = self._fonts["sec_body"]
        ls = self._line_spacing
        x = tl[0]
        right = br[0]
        width = right - x

        vessel_type_raw = (vessel.get("ship_type_name") or "").split(" - ", 1)[0].lower()
        vessel_type = vessel_type_raw if vessel_type_raw not in ("", "unknown", "reserved", "other") else "vessel"
        type_text = f"A {vessel_type} passed at {datetime.datetime.now().strftime('%H:%M')}"
        name_text = vessel.get("name", "")

        country = mmsi_country(vessel.get("identifier", ""))
        vessel_width = vessel.get("port", 0) + vessel.get("starboard", 0)
        vessel_length = vessel.get("stern", 0) + vessel.get("bow", 0)
        vessel_draught = vessel.get("draught", 0)

        info_items = []
        if country:
            info_items.append(country)
        info_items.append(f"{vessel_length}m × {vessel_width}m")
        if vessel_draught:
            info_items.append(f"{vessel_draught}m draught")

        type_h, _, _ = self._draw_text(draw, x, tl[1] + ls, type_text, subheader_font)
        name_top = tl[1] + ls + type_h + ls

        info_lh = self._line_height(body_font)
        info_y = br[1] - ls - info_lh
        mid = x + width // 2
        if len(info_items) == 1:
            self._draw_text(draw, x, info_y, info_items[0], body_font)
        elif len(info_items) == 2:
            self._draw_text(draw, x, info_y, info_items[0], body_font)
            self._draw_text(draw, right, info_y, info_items[1], body_font, halign="right")
        else:
            self._draw_text(draw, x, info_y, info_items[0], body_font)
            self._draw_text(draw, mid, info_y, info_items[1], body_font, halign="centre")
            self._draw_text(draw, right, info_y, info_items[2], body_font, halign="right")

        name_avail = (info_y - ls) - name_top

        if self._profile == "compact":
            max_px = max(FONT_FLOOR, round(64 * self._scale))
            min_px = max(FONT_FLOOR, round(22 * self._scale))
            if name_wrap and " " in name_text:
                # Two balanced lines, each sized to fit the wider one. Advance by
                # cap height + a small gap (not the full font line box) so the
                # lines sit close together, matching the large title.
                lines = split_two(name_text)
                widest = max(lines, key=lambda ln: self._fonts["pri_header"].getbbox(ln)[2])
                name_font = self._fit_font("primary", "400", widest, width, max_px, min_px)
                cap_h = self._ink_bottom(name_font, "M") - self._ink_top(name_font, "M")
                line_adv = cap_h + self._wrap_gap()
                block_h = cap_h + line_adv
                cursor = name_top + max(0, (name_avail - block_h) // 2)
                for ln in lines:
                    self._draw_text(draw, x, cursor - self._ink_top(name_font, ln), ln, name_font)
                    cursor += line_adv
            else:
                # Single line, sized to fit the width.
                name_font = self._fit_font("primary", "400", name_text, width, max_px, min_px)
                name_lh = self._line_height(name_font)
                y = name_top + max(0, (name_avail - name_lh) // 2)
                self._draw_text(draw, x, y, name_text, name_font)
            return

        # Standard: full-size header font, wrapping onto a second line (on the
        # first space) when the name is too wide rather than shrinking it.
        header_font = self._fonts["pri_header"]
        name_lh = self._line_height(header_font)

        bbox = header_font.getbbox(name_text)
        if bbox[2] - bbox[0] > width and " " in name_text:
            name_text = name_text.replace(" ", "\n", 1)

        lines = name_text.split("\n")
        n = len(lines)
        if n == 1:
            y = name_top + max(0, (name_avail - name_lh) // 2)
            self._draw_text(draw, x, y, lines[0], header_font)
        else:
            # Divide space into equal slots, centre each line's ink in its slot.
            slot_h = name_avail // n
            for i, line in enumerate(lines):
                ink_bbox = header_font.getbbox(line)
                ink_top, ink_h = ink_bbox[1], ink_bbox[3] - ink_bbox[1]
                slot_top = name_top + i * slot_h
                y = slot_top + (slot_h - ink_h) // 2 - ink_top
                self._draw_text(draw, x, y, line, header_font)

    # --- info band (position / destination / movement) ---------------------
    def _draw_vessel_highlights(self, draw: ImageDraw.ImageDraw, tl, br, vessel) -> None:
        """Three info groups. Compact uses an ink-spaced, divider-less band that
        fills the available height; other profiles use the divider layout."""
        lf = self._fonts
        x = tl[0]
        right = br[0]
        total_h = br[1] - tl[1]

        if self._profile == "compact":
            # Spread the info groups to fill the band: the four big gaps (top,
            # between each group, bottom) absorb whatever space exceeds the
            # tight core content, so rows breathe and top/bottom gaps stay equal.
            band_h = br[1] - tl[1]
            core = self._info_core_height(x, right, vessel)
            G = max(self._gap_small, (band_h - core) // 4)
            self._layout_compact_info(x, right, tl[1], vessel, draw=draw, gap_big=G)
            return

        divider_w = 2

        pos_h = self._block_h(lf["sec_header_semibold"], lf["sec_bigheader"])
        move_h = self._block_h(lf["sec_header_semibold"], lf["pri_title"])
        dest_avail = total_h - pos_h - move_h - 2 * divider_w

        dest_content_h = self._block_h(lf["sec_header_semibold"], lf["pri_title"], lf["sec_body"])
        dest_v_offset = max(0, (dest_avail - dest_content_h) // 2)

        self._draw_position_section(draw, (x, tl[1]), (right, tl[1] + pos_h), vessel)

        y = tl[1] + pos_h
        if divider_w:
            draw.line([(x, y), (right, y)], self._palette["line"], divider_w)

        dest_y = y + divider_w + dest_v_offset
        lower_divider_y = tl[1] + pos_h + divider_w + dest_avail
        self._draw_destination_section(draw, (x, dest_y), (right, lower_divider_y), vessel)

        y = lower_divider_y
        if divider_w:
            draw.line([(x, y), (right, y)], self._palette["line"], divider_w)

        y = tl[1] + pos_h + divider_w + dest_avail + divider_w
        self._draw_movement_section(draw, (x, y), (right, y + move_h), vessel)

    def _dest_parts(self, vessel, width):
        """Destination label/text/font + nav status + ETA for the info band."""
        raw = (vessel.get("destination") or "").strip()
        if raw:
            label, dest = "BOUND FOR", raw.upper()
        else:
            label, dest = "DETECTED IN", f"{self._zone_name} waters".upper()
        eta = vessel.get("eta")
        status_num = vessel.get("status")
        status_text = nav_status_label(status_num).upper()
        max_px = max(FONT_FLOOR, round(28 * self._scale))
        min_px = max(FONT_FLOOR, round(14 * self._scale))
        dest_font = self._fit_font("primary", "700", dest, width, max_px, min_px)
        return label, dest, dest_font, status_text, eta

    def _info_core_height(self, x, right, vessel) -> int:
        """Height of the three info groups stacked with no big gaps (G = 0)."""
        return self._layout_compact_info(x, right, 0, vessel, gap_big=0, draw=None)

    def _compact_highlights_height(self, vessel=None) -> int:
        """Natural info-band height (core groups + the four big gaps)."""
        v = vessel if vessel is not None else _SAMPLE_VESSEL
        return self._info_core_height(0, 1000, v) + 4 * self._gap_big

    def _layout_compact_info(self, x, right, top_y, vessel, draw=None, gap_big=None) -> int:
        """Lay out (and optionally draw) the three info groups, returning the
        band height. Spacing is measured between glyph *ink*, not font line
        boxes: a value's caps sit `gap_small` below its label's baseline, and
        groups are separated by `gap_big`. This keeps the visual rhythm tight
        and independent of each font's internal leading.
        """
        lf = self._fonts
        width = right - x
        mid = x + width // 2
        g = self._gap_small
        G = self._gap_big if gap_big is None else gap_big
        header_f = lf["sec_header_semibold"]

        def put(xx, ink_top, text, font, halign="left", baseline_y=None):
            """Draw so the glyph ink-top lands on `ink_top`; return (ink_bottom, baseline)."""
            ascender_top = ink_top - self._ink_top(font, text)
            if draw is not None:
                self._draw_text(draw, xx, ascender_top, text, font, halign=halign, baseline_y=baseline_y)
            baseline = ascender_top + font.getmetrics()[0]
            return ascender_top + self._ink_bottom(font, text), baseline

        cursor = top_y + G

        # Position: LATITUDE / LONGITUDE
        lat, lon = vessel.get("lat"), vessel.get("lon")
        lat_text = fmt_lat(lat) if lat is not None else "-"
        lon_text = fmt_lon(lon) if lon is not None else "-"
        _, bl = put(x, cursor, "LATITUDE", header_f)
        put(mid, cursor, "LONGITUDE", header_f)
        ib1, _ = put(x, bl + g, lat_text, lf["sec_bigheader"])
        ib2, _ = put(mid, bl + g, lon_text, lf["sec_bigheader"])
        cursor = max(ib1, ib2) + G

        # Destination: label / name (left aligned) / status + ETA
        label, dest, dest_font, status_text, eta = self._dest_parts(vessel, width)
        _, bl = put(x, cursor, label, header_f)
        dib, _ = put(x, bl + g, dest, dest_font)
        cursor = dib
        if status_text or eta:
            sib = dib + g
            if status_text:
                sib, _ = put(x, dib + g, status_text, lf["sec_body"])
            if eta:
                eib, _ = put(right, dib + g, f"ETA {eta}", lf["sec_body"], halign="right")
                sib = max(sib, eib)
            cursor = sib
        cursor += G

        # Movement: SPEED / COURSE / HEADING
        speed = vessel.get("speed", 0)
        course = vessel.get("course", 0)
        heading = vessel.get("heading", 511)
        _, bl = put(x, cursor, "SPEED", header_f)
        put(mid, cursor, "COURSE", header_f, halign="centre")
        put(right, cursor, "HEADING", header_f, halign="right")
        val_top = bl + g

        speed_str = f"{speed:g}"
        sib, sbl = put(x, val_top, speed_str, lf["pri_title"])
        sw = lf["pri_title"].getbbox(speed_str)[2] - lf["pri_title"].getbbox(speed_str)[0]
        put(x + sw + 2, val_top, "kn", lf["sec_body"], baseline_y=sbl)

        course_num = f"{course:g}°"
        course_dir = compass(course)
        w_num = lf["pri_title"].getbbox(course_num)[2] - lf["pri_title"].getbbox(course_num)[0]
        w_dir = lf["sec_body"].getbbox(course_dir)[2] - lf["sec_body"].getbbox(course_dir)[0]
        course_x = mid - (w_num + 2 + w_dir) // 2
        cib, cbl = put(course_x, val_top, course_num, lf["pri_title"])
        put(course_x + w_num + 2, val_top, course_dir, lf["sec_body"], baseline_y=cbl)

        heading_str = f"{int(round(heading))}°" if heading != 511 else "-"
        hib, _ = put(right, val_top, heading_str, lf["pri_title"], halign="right")

        cursor = max(sib, cib, hib) + G
        return cursor - top_y

    def _draw_position_section(self, draw: ImageDraw.ImageDraw, tl, br, vessel) -> None:
        header_font = self._fonts["sec_header_semibold"]
        body_font = self._fonts["sec_bigheader"]
        x = tl[0]
        right = br[0]
        mid = x + (right - x) // 2
        ls = self._line_spacing

        lat = vessel.get("lat")
        lon = vessel.get("lon")
        lat_text = fmt_lat(lat) if lat is not None else "-"
        lon_text = fmt_lon(lon) if lon is not None else "-"

        y = tl[1] + ls
        h, _, _ = self._draw_text(draw, x, y, "LATITUDE", header_font)
        self._draw_text(draw, mid, y, "LONGITUDE", header_font)
        y += h + ls
        self._draw_text(draw, x, y, lat_text, body_font)
        self._draw_text(draw, mid, y, lon_text, body_font)

    def _draw_destination_section(self, draw: ImageDraw.ImageDraw, tl, br, vessel) -> None:
        lf = self._fonts
        x = tl[0]
        right = br[0]
        width = right - x
        ls = self._line_spacing

        raw_dest = (vessel.get("destination") or "").strip()
        if raw_dest:
            label, destination = "BOUND FOR", raw_dest.upper()
        else:
            label, destination = "DETECTED IN", f"{self._zone_name} waters".upper()

        eta = vessel.get("eta")
        status_num = vessel.get("status")
        status_text = nav_status_label(status_num).upper()

        body_lh = self._line_height(lf["sec_body"])

        label_y = tl[1] + ls
        label_h, _, _ = self._draw_text(draw, x, label_y, label, lf["sec_header_semibold"])
        status_y = br[1] - ls - body_lh

        max_px = max(FONT_FLOOR, round(28 * self._scale))
        min_px = max(FONT_FLOOR, round(14 * self._scale))
        dest_font = self._fit_font("primary", "700", destination, width, max_px, min_px)
        dest_lh = self._line_height(dest_font)

        middle_top = label_y + label_h
        middle_bot = status_y - ls
        dest_y = middle_top + max(0, (middle_bot - middle_top - dest_lh) // 2)
        self._draw_text(draw, x + width // 2, dest_y, destination, dest_font, halign="centre")

        if status_text:
            self._draw_text(draw, x, status_y, status_text, lf["sec_body"])
        if eta:
            self._draw_text(draw, right, status_y, f"ETA {eta}", lf["sec_body"], halign="right")

    def _draw_movement_section(self, draw: ImageDraw.ImageDraw, tl, br, vessel) -> None:
        lf = self._fonts
        x = tl[0]
        right = br[0]
        width = right - x
        mid = x + width // 2
        ls = self._line_spacing

        speed = vessel.get("speed", 0)
        course = vessel.get("course", 0)
        heading = vessel.get("heading", 511)

        y = tl[1] + ls
        h, _, _ = self._draw_text(draw, x, y, "SPEED", lf["sec_header_semibold"])
        self._draw_text(draw, mid, y, "COURSE", lf["sec_header_semibold"], halign="centre")
        self._draw_text(draw, right, y, "HEADING", lf["sec_header_semibold"], halign="right")
        y += h + ls

        speed_str = f"{speed:g}"
        h, baseline, w = self._draw_text(draw, x, y, speed_str, lf["pri_title"])
        self._draw_text(draw, x + w + 2, y, "kn", lf["sec_body"], baseline_y=baseline)

        course_num = f"{course:g}°"
        course_dir = compass(course)
        w_num = lf["pri_title"].getbbox(course_num)[2] - lf["pri_title"].getbbox(course_num)[0]
        w_dir = lf["sec_body"].getbbox(course_dir)[2] - lf["sec_body"].getbbox(course_dir)[0]
        course_x = mid - (w_num + 2 + w_dir) // 2
        _, course_baseline, _ = self._draw_text(draw, course_x, y, course_num, lf["pri_title"])
        self._draw_text(draw, course_x + w_num + 2, y, course_dir, lf["sec_body"], baseline_y=course_baseline)

        heading_str = f"{int(round(heading))}°" if heading != 511 else "-"
        self._draw_text(draw, right, y, heading_str, lf["pri_title"], halign="right")

    def _draw_vessel_data(self, draw: ImageDraw.ImageDraw, tl, br, vessel) -> None:
        lf = self._fonts
        x = tl[0]
        right = br[0]
        width = right - x
        mid = x + width // 2
        ls = self._line_spacing

        mmsi = vessel.get("identifier", "")
        imo = vessel.get("imo", "")
        callsign = vessel.get("callsign", "")
        parts = [f"MMSI {mmsi}"] if mmsi else []
        if imo:
            parts.append(f"IMO {imo}")
        if callsign:
            parts.append(f"Callsign {callsign.strip()}")

        self._draw_text(draw, x, tl[1] + ls, parts[0], lf["sec_body"])
        if len(parts) == 2:
            self._draw_text(draw, right, tl[1] + ls, parts[1], lf["sec_body"], halign="right")
        elif len(parts) >= 3:
            self._draw_text(draw, mid, tl[1] + ls, parts[1], lf["sec_body"], halign="centre")
            self._draw_text(draw, right, tl[1] + ls, parts[2], lf["sec_body"], halign="right")

    def _draw_vessel_diagram(
        self,
        draw: ImageDraw.ImageDraw,
        tl,
        br,
        vessel: dict[str, Any],
    ) -> None:
        x, y = tl
        box_width = br[0] - tl[0]
        box_height = br[1] - tl[1]

        ship_stern = vessel.get("stern", 0)
        ship_bow = vessel.get("bow", 0)
        ship_port = vessel.get("port", 0)
        ship_starboard = vessel.get("starboard", 0)

        ship_len = ship_stern + ship_bow
        ship_wid = ship_port + ship_starboard

        if ship_len == 0 or ship_wid == 0:
            return

        border_padding = self._ship_diagram_padding
        inner_x = x + border_padding
        inner_y = y + border_padding
        inner_width = box_width - border_padding * 2
        inner_height = box_height - border_padding * 2

        ship_padding = self._ship_inner_padding
        available_width = inner_width - ship_padding * 2
        available_height = inner_height - ship_padding * 2

        scale_factor = min(available_width / ship_len, available_height / ship_wid)
        scaled_len = int(ship_len * scale_factor)
        scaled_wid = int(ship_wid * scale_factor)

        ship_centre_x = inner_x + ship_padding + available_width / 2
        ship_centre_y = inner_y + ship_padding + available_height / 2

        self._draw_ship_outline(draw, ship_centre_x, ship_centre_y, scaled_len, scaled_wid)

        dot_x = (ship_centre_x - scaled_len / 2) + ship_stern * scale_factor
        dot_y = (ship_centre_y - scaled_wid / 2) + ship_port * scale_factor
        r = self._mast_size / 2
        draw.ellipse([dot_x - r, dot_y - r, dot_x + r, dot_y + r], fill=self._palette["accent"])

    def _draw_ship_outline(
        self,
        draw: ImageDraw.ImageDraw,
        centre_x: float,
        centre_y: float,
        scaled_len: int,
        scaled_wid: int,
    ) -> None:
        nose_ratio = 0.6 * (scaled_wid / scaled_len)
        nose_len = scaled_len * nose_ratio
        half_len = scaled_len / 2
        half_wid = scaled_wid / 2
        line_width = max(1, int(2 * self._scale))

        points = [
            (centre_x - half_len, centre_y - half_wid),
            (centre_x + half_len - nose_len, centre_y - half_wid),
            (centre_x + half_len, centre_y),
            (centre_x + half_len - nose_len, centre_y + half_wid),
            (centre_x - half_len, centre_y + half_wid),
        ]
        draw.polygon(points, outline=self._palette["line"], width=line_width)


def get_config_schema() -> ConfigSchema:
    return ConfigSchema(
        plugin_name="zone_screen",
        plugin_type="screen",
        fields=[
            ConfigField(
                key="zone_name",
                label="Zone Name",
                field_type=ConfigFieldType.STRING,
                default="zone"
            ),
            ConfigField(
                key="zone",
                label="Zone",
                field_type=ConfigFieldType.ZONE,
                default=None,
                required=False,
                description="Centre position and radius of the monitoring zone",
            ),
            ConfigField(
                key="heading_offset",
                label="Heading Offset",
                field_type=ConfigFieldType.INTEGER,
                default=0,
                required=False,
                description="Degrees to rotate the 13\" landscape compass rose so its "
                            "orientation matches how the frame physically faces.",
            ),
        ],
    )


def make_plugin(**kwargs: Any) -> ScreenPlugin:
    return ZoneScreen(**kwargs)
