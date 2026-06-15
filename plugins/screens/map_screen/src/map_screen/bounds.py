"""Geographic bounds for the map screen.

A small util class so the map layout and tile cache share the same geo maths
without depending on each other.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Bounds:
    """A geographic bounding box (decimal degrees)."""

    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float

    @classmethod
    def parse(cls, bounds: dict | None, logger) -> Bounds:
        """Build from a config dict, warning on (and ignoring) incomplete input."""
        keys = ("min_lat", "max_lat", "min_lon", "max_lon")
        if bounds and not all(k in bounds for k in keys):
            logger.warning(
                f"Map bounds config is missing required keys "
                f"{[k for k in keys if k not in bounds]}. Bounds will be ignored."
            )
            bounds = None
        if not bounds:
            return cls(0.0, 0.0, 0.0, 0.0)
        return cls(float(bounds["min_lat"]), float(bounds["max_lat"]),
                   float(bounds["min_lon"]), float(bounds["max_lon"]))

    @property
    def valid(self) -> bool:
        return self.max_lat > self.min_lat and self.max_lon > self.min_lon

    def contains(self, lat: float, lon: float) -> bool:
        return self.min_lat <= lat <= self.max_lat and self.min_lon <= lon <= self.max_lon

    def project(self, lat: float, lon: float, w: int, h: int) -> tuple[float, float]:
        """Project lat/lon to pixel coords within a (w, h) plate (origin top-left)."""
        x = ((lon - self.min_lon) / (self.max_lon - self.min_lon)) * w
        y = h - ((lat - self.min_lat) / (self.max_lat - self.min_lat)) * h
        return x, y

    def metres_per_pixel(self, plate_w: int, plate_h: int) -> float:
        """Metres per pixel for the plate, from the bounds and plate dimensions."""
        metres_per_degree_lat = 111_320
        centre_lat = (self.min_lat + self.max_lat) / 2
        metres_per_degree_lon = metres_per_degree_lat * math.cos(math.radians(centre_lat))
        lat_range_m = (self.max_lat - self.min_lat) * metres_per_degree_lat
        lon_range_m = (self.max_lon - self.min_lon) * metres_per_degree_lon
        return max(lat_range_m / plate_h, lon_range_m / plate_w)
