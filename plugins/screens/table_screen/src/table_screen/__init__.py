from __future__ import annotations
import asyncio
import time
from typing import Any
from contextlib import suppress
from PIL import ImageDraw
import logging

from vf_core.message_bus import MessageBus
from vf_core.plugin_types import ConfigField, ConfigFieldType, ConfigSchema, ScreenPlugin, RendererPlugin, require_plugin_args
from vf_core.vessel_manager import VesselManager
from vf_core.asset_manager import AssetManager
from vf_core.render_strategies import PeriodicRenderStrategy
from vf_core.text_utils import TextRenderingMixin

from .common import TableCommon
from .large import LargeTableLayout
from .landscape import LandscapeTableLayout

# Layout profile is chosen by the panel's short side (min of width/height, px):
# at/above LARGE_MIN the broadsheet "large" layout; below MEDIUM_MIN the tight
# single-column "small" layout; else "medium" (small + a speed column).
PROFILE_LARGE_MIN = 1000
PROFILE_MEDIUM_MIN = 480

# Design reference widths per profile (the panel's long edge), per orientation;
# fonts/spacing scale from these so each launch resolution renders at scale 1.0.
REF_WIDTH = {"small": 400, "medium": 480, "large": 1200}
REF_WIDTH_LANDSCAPE = {"small": 600, "medium": 800, "large": 1600}

# Upper bound on vessels pulled per render; the layout shows as many as fit.
FETCH_LIMIT = 500


class TableScreen(ScreenPlugin, TextRenderingMixin, TableCommon, LargeTableLayout, LandscapeTableLayout):
    """Screen showing a broadsheet table of recently observed vessels.

    The layout adapts to the canvas size by selecting one of three profiles
    (small / medium / large) and scaling fonts and spacing to fit, so a single
    drawing codebase serves every supported display.
    """

    def __init__(
        self,
        *,
        bus: MessageBus,
        renderer: RendererPlugin,
        vm: VesselManager,
        asset_manager: AssetManager,
        in_topic: str = "vessel.updated",
        update_interval: float = 30.0,
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

        interval = float(update_interval) if isinstance(update_interval, str) else update_interval
        self._render_strategy = PeriodicRenderStrategy(
            self._render, max(interval, renderer.MIN_RENDER_INTERVAL)
        )

        canvas_w, canvas_h = renderer.canvas.size
        self._orientation = "landscape" if canvas_w > canvas_h else "portrait"
        self._profile = self._select_profile(canvas_w, canvas_h)
        refs = REF_WIDTH_LANDSCAPE if self._orientation == "landscape" else REF_WIDTH
        self._scale = canvas_w / refs[self._profile]
        self._line_w = max(1, round(2 * self._scale))
        self._gap = max(1, round(16 * self._scale))
        self._gap_s = max(1, round(5 * self._scale))

    # --- profile + scaling -------------------------------------------------
    def _select_profile(self, w: int, h: int) -> str:
        """Pick a layout profile from the panel's short side."""
        cross = min(w, h)
        if cross >= PROFILE_LARGE_MIN:
            return "large"
        if cross < PROFILE_MEDIUM_MIN:
            return "small"
        return "medium"

    def _px(self, v: float) -> int:
        return max(1, round(v * self._scale))

    # --- lifecycle ---------------------------------------------------------
    async def activate(self) -> None:
        """Start listening for updates and enable periodic rendering."""
        if self._task and not self._task.done():
            return

        await self._render_strategy.start()
        self._render_strategy.request_render()
        self._task = asyncio.create_task(self._update_loop())

    async def deactivate(self) -> None:
        """Stop listening for updates and cancel pending work."""
        if self._task and not self._task.done():
            await self._render_strategy.stop()

            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _update_loop(self) -> None:
        """Internal loop that receives update events and requests renders."""
        try:
            async for msg in self._bus.subscribe(self._in_topic):
                self._render_strategy.request_render()
        except asyncio.CancelledError:
            raise
        except Exception:
            self._logger.exception("Update loop crashed")
            raise

    # --- layout driver -----------------------------------------------------
    async def _render(self) -> None:
        """Render the table of most recently observed vessels."""
        vessels = self._vessel_manager.get_recent_vessels(limit=FETCH_LIMIT)
        total = len(vessels)
        large = self._profile == "large"
        show_speed = self._profile == "medium"
        if self._orientation == "landscape":
            if large:
                await self._render_landscape_large(vessels, total)
            else:
                await self._render_landscape_list(vessels, total, show_speed=show_speed)
        elif large:
            await self._render_large(vessels, total)
        else:
            await self._render_list(vessels, total, show_speed=show_speed)

    async def _render_list(self, vessels: list[dict], total: int, show_speed: bool) -> None:
        """Small / medium portrait list: two-line rows, optional speed column."""
        canvas = self._renderer.canvas
        draw = ImageDraw.Draw(canvas)
        W, H = canvas.size
        px = self._px
        P = self._palette
        line = P["line"]
        am = self._asset_manager
        now = time.time()
        small = self._profile == "small"

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


def get_config_schema() -> ConfigSchema:
    """Return the config schema for this plugin.

    Defines editable fields for the admin panel.

    Returns:
        ConfigSchema: Schema describing this plugin's configuration options.
    """
    return ConfigSchema(
        plugin_name="table_screen",
        plugin_type="screen",
        fields=[
            ConfigField(
                key="update_interval",
                label="Min Update Interval",
                field_type=ConfigFieldType.FLOAT,
                default=300.0
            ),
        ],
    )


def make_plugin(**kwargs: Any) -> ScreenPlugin:
    """Factory function for plugin system"""
    return TableScreen(**kwargs)
