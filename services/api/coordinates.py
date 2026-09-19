"""Small, testable geographic-to-floor coordinate transformations.

The tracker receives latitude/longitude from a browser.  This module keeps
that geographic math out of the API handlers and, importantly, makes the
assumptions explicit: this is a local tangent approximation for a
building-scale test deployment, not a survey-grade projection.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


METERS_PER_DEGREE_LATITUDE = 111_320.0


@dataclass(frozen=True)
class CalibrationReference:
    reference_latitude: float
    reference_longitude: float
    reference_floor_x: float
    reference_floor_y: float
    yaw_deg: float = 0.0
    calibration_id: str = "demo-origin"
    label: str = "Demo Start"


def local_east_north_m(
    latitude: float,
    longitude: float,
    reference_latitude: float,
    reference_longitude: float,
) -> tuple[float, float]:
    """Return east/north displacement in metres from a reference point."""

    north_m = (latitude - reference_latitude) * METERS_PER_DEGREE_LATITUDE
    latitude_scale = math.cos(math.radians(reference_latitude))
    east_m = (
        (longitude - reference_longitude)
        * METERS_PER_DEGREE_LATITUDE
        * latitude_scale
    )
    return east_m, north_m


def geographic_to_floor(
    latitude: float,
    longitude: float,
    reference: CalibrationReference,
) -> tuple[float, float]:
    """Convert a browser coordinate into Seuranta floor-local X/Y metres.

    At yaw 0, east maps to floor X and north maps to floor Y.  A positive yaw
    rotates the east/north vector counter-clockwise into the configured local
    floor axes.
    """

    east_m, north_m = local_east_north_m(
        latitude,
        longitude,
        reference.reference_latitude,
        reference.reference_longitude,
    )
    angle = math.radians(reference.yaw_deg)
    floor_x = reference.reference_floor_x + east_m * math.cos(angle) - north_m * math.sin(angle)
    floor_y = reference.reference_floor_y + east_m * math.sin(angle) + north_m * math.cos(angle)
    return floor_x, floor_y


def is_outside_map(
    x_m: float,
    y_m: float,
    width_m: float,
    depth_m: float,
    origin_x_m: float = 0.0,
    origin_y_m: float = 0.0,
) -> bool:
    """Return whether a point lies outside the configured rectangular floor."""

    return not (
        origin_x_m <= x_m <= origin_x_m + width_m
        and origin_y_m <= y_m <= origin_y_m + depth_m
    )
