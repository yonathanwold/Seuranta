"""Floor-zone assignment shared by the phone positioning path."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ZonePolygon:
    zone_id: str
    name: str
    polygon: tuple[tuple[float, float], ...]


# The current frontend floor definition contains one modeled circulation
# polygon.  Keeping this small fallback here avoids duplicating a large room
# catalog while leaving a clear seam for a shared JSON floor definition later.
DEFAULT_ZONES: tuple[ZonePolygon, ...] = (
    ZonePolygon(
        zone_id="main-circulation",
        name="Main circulation",
        polygon=(
            (2.4, 30.7),
            (11.6, 30.7),
            (11.6, 31.0),
            (63.7, 31.0),
            (63.7, 33.2),
            (70.8, 33.2),
            (70.8, 26.5),
            (62.0, 25.6),
            (48.0, 24.2),
            (18.0, 21.0),
            (7.4, 20.0),
            (7.4, 24.0),
            (2.9, 23.2),
        ),
    ),
)


def point_in_polygon(x_m: float, y_m: float, polygon: tuple[tuple[float, float], ...]) -> bool:
    """Ray-casting point-in-polygon test for floor-local metres."""

    inside = False
    if len(polygon) < 3:
        return False
    previous_x, previous_y = polygon[-1]
    for current_x, current_y in polygon:
        crosses = (current_y > y_m) != (previous_y > y_m)
        if crosses:
            intersection_x = (previous_x - current_x) * (y_m - current_y) / (previous_y - current_y) + current_x
            if x_m < intersection_x:
                inside = not inside
        previous_x, previous_y = current_x, current_y
    return inside


def assign_zone(
    x_m: float,
    y_m: float,
    zones: tuple[ZonePolygon, ...] = DEFAULT_ZONES,
) -> str | None:
    for zone in zones:
        if point_in_polygon(x_m, y_m, zone.polygon):
            return zone.zone_id
    return None
