"""Danger zones: manually configured polygons in image space (FR-03).

Polygon vertices are stored **normalised** to 0–1 of the frame width/height so
a zone stays correct when frames are downscaled for inference. Zones describe
image regions only. They say nothing about real-world distances.

A worker is "in" a zone when the bottom-centre of their bounding box (their
feet, see ``Detection.foot_point``) lies inside or on the edge of the polygon.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

Point = tuple[float, float]


class ZoneConfigError(ValueError):
    """Raised for malformed zone definitions."""


@dataclass(frozen=True)
class DangerZone:
    zone_id: str
    name: str
    polygon: tuple[Point, ...]  # normalised (x, y) in [0, 1]
    source_name: str | None = None  # video/camera this zone belongs to; None = any

    def __post_init__(self) -> None:
        if len(self.polygon) < 3:
            raise ZoneConfigError(f"Zone '{self.zone_id}' needs at least 3 points")
        for x, y in self.polygon:
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                raise ZoneConfigError(
                    f"Zone '{self.zone_id}' has point ({x}, {y}) outside the normalised 0-1 range"
                )

    def pixel_polygon(self, width: int, height: int) -> list[tuple[int, int]]:
        return [(round(x * width), round(y * height)) for x, y in self.polygon]

    def contains_pixel(self, point: Point, width: int, height: int) -> bool:
        """Is a pixel-space point inside this zone on a ``width`` x ``height`` frame?"""
        if width <= 0 or height <= 0:
            return False
        return point_in_polygon((point[0] / width, point[1] / height), self.polygon)

    def to_dict(self) -> dict:
        return {
            "zone_id": self.zone_id,
            "name": self.name,
            "polygon": [list(p) for p in self.polygon],
            "source_name": self.source_name,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DangerZone:
        try:
            polygon = tuple((float(x), float(y)) for x, y in data["polygon"])
            return cls(
                zone_id=str(data["zone_id"]),
                name=str(data.get("name") or data["zone_id"]),
                polygon=polygon,
                source_name=data.get("source_name"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, ZoneConfigError):
                raise
            raise ZoneConfigError(f"Invalid zone definition: {exc}") from exc

    @classmethod
    def from_pixels(
        cls,
        zone_id: str,
        points: Iterable[Point],
        width: int,
        height: int,
        *,
        name: str | None = None,
        source_name: str | None = None,
    ) -> DangerZone:
        """Build a zone from pixel coordinates measured on a ``width`` x ``height`` frame."""
        polygon = tuple((x / width, y / height) for x, y in points)
        return cls(zone_id=zone_id, name=name or zone_id, polygon=polygon, source_name=source_name)


def _on_segment(p: Point, a: Point, b: Point, eps: float = 1e-9) -> bool:
    cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    if abs(cross) > eps:
        return False
    return (
        min(a[0], b[0]) - eps <= p[0] <= max(a[0], b[0]) + eps
        and min(a[1], b[1]) - eps <= p[1] <= max(a[1], b[1]) + eps
    )


def point_in_polygon(point: Point, polygon: Sequence[Point]) -> bool:
    """Ray-casting test. Points on an edge or vertex count as inside.

    Counting the boundary as inside is deliberate: a missed hazard is worse
    than a false alarm.
    """
    n = len(polygon)
    if n < 3:
        return False
    x, y = point
    inside = False
    for i in range(n):
        a, b = polygon[i], polygon[(i + 1) % n]
        if _on_segment(point, a, b):
            return True
        if (a[1] > y) != (b[1] > y):
            x_cross = a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if x < x_cross:
                inside = not inside
    return inside


def parse_zone_arg(text: str, *, zone_id: str = "zone-1", source_name: str | None = None) -> DangerZone:
    """Parse ``"x1,y1;x2,y2;x3,y3"`` (normalised 0-1 values) from the command line."""
    try:
        points = tuple(
            (float(x), float(y))
            for x, y in (pair.split(",") for pair in text.split(";") if pair.strip())
        )
    except ValueError as exc:
        raise ZoneConfigError(f"Zone must look like 'x1,y1;x2,y2;x3,y3', got {text!r}") from exc
    return DangerZone(zone_id=zone_id, name=zone_id, polygon=points, source_name=source_name)


def load_zones(path: str | Path) -> list[DangerZone]:
    """Load zones from a JSON file: ``{"zones": [{"zone_id", "name", "polygon", "source_name"}]}``."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ZoneConfigError(f"Could not read zone file {path.name}: {exc}") from exc
    items = data.get("zones") if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        raise ZoneConfigError(f"Zone file {path.name} contains no zones")
    zones = [DangerZone.from_dict(item) for item in items]
    ids = [z.zone_id for z in zones]
    if len(ids) != len(set(ids)):
        raise ZoneConfigError(f"Zone file {path.name} has duplicate zone_id values")
    return zones


def save_zones(path: str | Path, zones: Iterable[DangerZone]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"zones": [z.to_dict() for z in zones]}, indent=2), encoding="utf-8")


def zones_for_source(zones: Iterable[DangerZone], source_name: str) -> list[DangerZone]:
    """Zones tied to ``source_name``, plus zones that apply to any source."""
    return [z for z in zones if z.source_name in (None, source_name)]
