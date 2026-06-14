"""Mapbox static-map plate image utils.

Plate images for both orientations are cached under data_dir/map_cache,
named by bounds + style + plate size (normalised, so flipping orientation
reuses the same entries).
"""
from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

from PIL import Image

from .bounds import Bounds


class MapImageCache:
    """Downloads/caches/loads the plate-sized map images for both orientations."""

    DOWNLOAD_TIMEOUT: float = 30.0
    # Mapbox Static Images API caps each edge at 1280px so larger plates use @2x.
    MAPBOX_MAX_EDGE: int = 1280

    def __init__(
        self,
        *,
        cache_dir: Path,
        map_style: str,
        mapbox_key: str,
        bounds: Bounds,
        portrait_plate: tuple[int, int],
        landscape_plate: tuple[int, int],
        logger,
    ) -> None:
        self._cache_dir = cache_dir
        self._map_style = map_style
        self._mapbox_key = mapbox_key
        self._bounds = bounds
        self._portrait_plate = portrait_plate
        self._landscape_plate = landscape_plate
        self._logger = logger
        self._portrait: Image.Image | None = None
        self._landscape: Image.Image | None = None

        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_key = self._compute_cache_key()
        self._cleanup_stale_cache()

    @property
    def loaded(self) -> bool:
        return self._portrait is not None and self._landscape is not None

    def current(self, is_portrait: bool) -> Image.Image | None:
        """The plate image for the current canvas orientation."""
        return self._portrait if is_portrait else self._landscape

    def ensure(self) -> None:
        """Download plate-sized map images for both orientations if missing."""
        if not self._bounds.valid:
            return
        for name, (width, height) in (("map_portrait", self._portrait_plate),
                                      ("map_landscape", self._landscape_plate)):
            img_path = self._cache_dir / f"{name}_{self._cache_key}"
            if self._is_valid_image(img_path):
                continue
            if len(self._mapbox_key) == 0:
                self._logger.error("No Mapbox Key set - unable to download image")
                continue
            self._download(name, width, height, img_path)

    def load(self) -> None:
        """Load both cached images into memory (RGB)."""
        self._portrait = self._load_map_image("map_portrait")
        self._landscape = self._load_map_image("map_landscape")

    # --- internals ---------------------------------------------------------
    def _compute_cache_key(self) -> str:
        """Short hash of the params that affect the map image (bounds, style,
        plate size). Plate dims are normalised to [short, long] so flipping
        orientation reuses the same entries."""
        pw, ph = self._portrait_plate
        short_edge, long_edge = min(pw, ph), max(pw, ph)
        b = self._bounds
        key_data = (
            f"{b.min_lat}:{b.max_lat}:{b.min_lon}:{b.max_lon}"
            f":{self._map_style}:{short_edge}x{long_edge}"
        )
        return hashlib.sha256(key_data.encode()).hexdigest()[:12]

    def _cleanup_stale_cache(self) -> None:
        """Remove cached map files that don't match the current cache key."""
        for path in self._cache_dir.iterdir():
            if path.name.startswith(("map_portrait_", "map_landscape_")) and \
                    not path.name.endswith(f"_{self._cache_key}"):
                self._logger.info(f"Removing stale cache file: {path.name}")
                path.unlink(missing_ok=True)

    def _download(self, name: str, width: int, height: int, img_path: Path) -> None:
        req_w, req_h, retina = self._compute_request_params(width, height)
        self._logger.info(f"Downloading map image: {name}")
        try:
            b = self._bounds
            bounds_str = f"[{b.min_lon},{b.min_lat},{b.max_lon},{b.max_lat}]"
            url = (
                f"https://api.mapbox.com/styles/v1/{self._map_style}/static/"
                f"{bounds_str}/{req_w}x{req_h}{retina}?access_token={self._mapbox_key}"
            )
            self._logger.debug(f"Mapbox URL: {url}")
            tmp_path = img_path.with_suffix(".tmp")
            try:
                with urllib.request.urlopen(url, timeout=self.DOWNLOAD_TIMEOUT) as response:
                    tmp_path.write_bytes(response.read())
                tmp_path.replace(img_path)
            except Exception:
                tmp_path.unlink(missing_ok=True)
                raise
            self._logger.info(f"Downloaded map image: {img_path}")
        except Exception:
            self._logger.exception(f"Failed to download map image: {name}")

    def _compute_request_params(self, width: int, height: int) -> tuple[int, int, str]:
        """Return (request_width, request_height, retina_suffix) for a Mapbox URL.

        Mapbox caps each dimension at 1280. When either edge exceeds that we use
        @2x: dimension params are halved and Mapbox returns a 2x-density image,
        so the final pixel size matches the plate exactly.
        """
        if max(width, height) > self.MAPBOX_MAX_EDGE:
            req_w = (width + 1) // 2
            req_h = (height + 1) // 2
            if max(req_w, req_h) > self.MAPBOX_MAX_EDGE:
                self._logger.warning(
                    f"Plate dimensions {width}x{height} exceed Mapbox @2x limit. "
                    f"Image may be truncated or rejected."
                )
            return req_w, req_h, "@2x"
        return width, height, ""

    def _is_valid_image(self, path: Path) -> bool:
        """True if the file exists and can be fully decoded. Deletes if it's corrupted."""
        if not path.exists():
            return False
        try:
            with Image.open(path) as img:
                img.load()
            return True
        except Exception:
            self._logger.warning(f"Cached map image is corrupted, deleting: {path.name}")
            path.unlink(missing_ok=True)
            return False

    def _load_map_image(self, name: str) -> Image.Image | None:
        """Load a cached map image (RGB) for compositing."""
        path = self._cache_dir / f"{name}_{self._cache_key}"
        if not self._is_valid_image(path):
            self._logger.warning(f"Map image not found: {path.name}")
            return None
        with Image.open(path) as img:
            img.load()
            return img.convert("RGB")
