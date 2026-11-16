"""Compact Position Reporting (CPR) decoding.

Implements DO-260B Annex A.1.7: airborne global (even/odd pair) and
local/relative (single frame + reference) decoding, plus the surface variants.
Airborne CPR spans 360 degrees of latitude; surface CPR spans 90 degrees.
"""

from __future__ import annotations

from math import acos, cos, floor, pi

_CPR_DENOM = 131072.0  # 2**17


def cpr_nl(lat: float) -> int:
    """Number of longitude zones (NL) for a latitude, per DO-260B A.1.7.2."""
    abs_lat = abs(lat)
    if abs_lat > 87.0:
        return 1
    if abs_lat == 87.0:
        return 2
    nz = 15
    a = 1.0 - cos(pi / (2 * nz))
    b = cos(pi / 180.0 * abs_lat) ** 2
    nl = 2 * pi / acos(1.0 - a / b)
    return min(59, max(1, int(floor(nl))))


def _local(lat_cpr: float, lon_cpr: float, lat_ref: float, lon_ref: float, fflag: bool, span: float):
    d_lat = span / 59.0 if fflag else span / 60.0
    j = floor(0.5 + lat_ref / d_lat - lat_cpr)
    lat = d_lat * (j + lat_cpr)
    ni = cpr_nl(lat) - (1 if fflag else 0)
    d_lon = span / ni if ni > 0 else span
    m = floor(0.5 + lon_ref / d_lon - lon_cpr)
    lon = d_lon * (m + lon_cpr)
    if lon > 180.0:
        lon -= 360.0
    return lat, lon


def airborne_local(lat_cpr: float, lon_cpr: float, lat_ref: float, lon_ref: float, fflag: bool):
    return _local(lat_cpr, lon_cpr, lat_ref, lon_ref, fflag, 360.0)


def surface_local(lat_cpr: float, lon_cpr: float, lat_ref: float, lon_ref: float, fflag: bool):
    return _local(lat_cpr, lon_cpr, lat_ref, lon_ref, fflag, 90.0)


def airborne_global(
    lat_e: float,
    lon_e: float,
    lat_o: float,
    lon_o: float,
    even_is_newer: bool = True,
) -> tuple[float, float] | None:
    """Globally unambiguous airborne position from an even/odd CPR pair.

    ``lat_*/lon_*`` are the fractional CPR values in ``[0, 1)``.  Returns
    ``(lat, lon)`` or ``None`` when no consistent solution exists.
    """
    j = floor(59 * lat_e - 60 * lat_o + 0.5)
    lat_even = (360.0 / 60) * (j % 60 + lat_e)
    lat_odd = (360.0 / 59) * (j % 59 + lat_o)
    if lat_even >= 270.0:
        lat_even -= 360.0
    if lat_odd >= 270.0:
        lat_odd -= 360.0
    if cpr_nl(lat_even) != cpr_nl(lat_odd):
        return None

    if even_is_newer:
        lat = lat_even
        nl = cpr_nl(lat)
        ni = max(nl, 1)
        m = floor(lon_e * (nl - 1) - lon_o * nl + 0.5)
        lon = (360.0 / ni) * (m % ni + lon_e)
    else:
        lat = lat_odd
        nl = cpr_nl(lat)
        ni = max(nl - 1, 1)
        m = floor(lon_e * (nl - 1) - lon_o * nl + 0.5)
        lon = (360.0 / ni) * (m % ni + lon_o)

    if lon > 180.0:
        lon -= 360.0
    if abs(lat) > 90.0 or abs(lon) > 180.0:
        return None
    return lat, lon


def surface_global(
    lat_e: float,
    lon_e: float,
    lat_o: float,
    lon_o: float,
    lat_ref: float,
    lon_ref: float,
    even_is_newer: bool = True,
) -> tuple[float, float] | None:
    """Surface position from an even/odd CPR pair using a receiver reference."""
    j = floor(59 * lat_e - 60 * lat_o + 0.5)
    lat_even_n = (90.0 / 60) * (j % 60 + lat_e)
    lat_odd_n = (90.0 / 59) * (j % 59 + lat_o)
    pairs = ((lat_even_n, lat_odd_n), (lat_even_n - 90.0, lat_odd_n - 90.0))
    newer = 0 if even_is_newer else 1
    lat_even, lat_odd = min(pairs, key=lambda p: abs(lat_ref - p[newer]))
    if cpr_nl(lat_even) != cpr_nl(lat_odd):
        return None

    if even_is_newer:
        lat = lat_even
        nl = cpr_nl(lat)
        ni = max(nl, 1)
        m = floor(lon_e * (nl - 1) - lon_o * nl + 0.5)
        lon_base = (90.0 / ni) * (m % ni + lon_e)
    else:
        lat = lat_odd
        nl = cpr_nl(lat)
        ni = max(nl - 1, 1)
        m = floor(lon_e * (nl - 1) - lon_o * nl + 0.5)
        lon_base = (90.0 / ni) * (m % ni + lon_o)

    candidates = [((lon_base + q + 180.0) % 360.0) - 180.0 for q in (0, 90, 180, 270)]
    lon = min(candidates, key=lambda c: abs((c - lon_ref + 180.0) % 360.0 - 180.0))
    return lat, lon
