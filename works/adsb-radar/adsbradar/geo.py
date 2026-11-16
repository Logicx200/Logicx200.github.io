"""Geodesy helpers for the radar PPI (azimuthal) projection.

The radar is drawn as an azimuthal projection centred on the receiver: every
target and every map vertex is reduced to a (range_km, bearing_deg) pair, which
is then plotted as (east_km, north_km) = (range*sin(bearing), range*cos(bearing)).
"""

from __future__ import annotations

import math

EARTH_R = 6371.0088  # mean Earth radius, km


def _rad(x: float) -> float:
    return math.radians(x)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two WGS84 points."""
    p1, p2 = _rad(lat1), _rad(lat2)
    dphi = _rad(lat2 - lat1)
    dl = _rad(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing (0..360, degrees from true north) from point 1 to 2."""
    p1, p2 = _rad(lat1), _rad(lat2)
    dl = _rad(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def project(lat0: float, lon0: float, lat1: float, lon1: float) -> tuple[float, float]:
    """Project point 1 into local (east_km, north_km) relative to origin 0."""
    d = haversine_km(lat0, lon0, lat1, lon1)
    b = _rad(bearing_deg(lat0, lon0, lat1, lon1))
    return d * math.sin(b), d * math.cos(b)


def offset(lat: float, lon: float, dist_km: float, brg_deg: float) -> tuple[float, float]:
    """Destination point a great-circle ``dist_km`` along ``brg_deg`` from a point."""
    d = dist_km / EARTH_R
    b = _rad(brg_deg)
    p1, l1 = _rad(lat), _rad(lon)
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(b))
    l2 = l1 + math.atan2(
        math.sin(b) * math.sin(d) * math.cos(p1),
        math.cos(d) - math.sin(p1) * math.sin(p2),
    )
    return math.degrees(p2), math.degrees(l2)
