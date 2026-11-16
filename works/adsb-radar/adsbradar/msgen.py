"""Mode S frame *builder* (encoder).

Used by the built-in simulator and by the test suite to produce well-formed
DF17/DF18 frames from plain fields, so the decoder and demodulator can be
verified end-to-end without a receiver.  It is intentionally the inverse of
``adsbradar.decode`` / ``adsbradar.cpr``.
"""

from __future__ import annotations

from math import cos, radians, sin

from .crc import crc24
from .cpr import cpr_nl
from .decode import CHARSET


def _assemble(df: int, ca: int, icao: int, me: int) -> bytes:
    b0 = (df << 3) | (ca & 0x07)
    data = bytes([b0]) + icao.to_bytes(3, "big") + me.to_bytes(7, "big")
    # The 24-bit parity equals the CRC of the 88 data bits (which already
    # include the ICAO address); the received-frame syndrome is then 0.
    pi = crc24(int.from_bytes(data, "big"), 88)
    return data + pi.to_bytes(3, "big")


def _altfield(alt_ft: int) -> int:
    n = int(round((alt_ft + 1000) / 25.0))
    n = max(0, min(2047, n))
    # 11-bit value n -> 13-bit altcode (insert M=0 at bit 6, Q=1 at bit 4)
    ac13 = ((n >> 5) << 7) | (((n >> 4) & 1) << 5) | (1 << 4) | (n & 0xF)
    # 13-bit altcode -> 12-bit AC field (drop the inserted M bit)
    return ((ac13 >> 7) << 6) | (ac13 & 0x3F)


def _cpr_frac(value: float, step: float) -> int:
    frac = (value % step) / step
    if frac >= 1.0:
        frac -= 1.0
    return int(round(frac * 131072.0)) & 0x1FFFF


def build_ident(icao: int, callsign: str, ca: int = 5, df: int = 17) -> bytes:
    me = 4 << 51  # TC = 4 (aircraft identification)
    cs = (callsign + " " * 8)[:8]
    for i, ch in enumerate(cs):
        idx = CHARSET.find(ch)
        if idx < 0:
            idx = 0
        me |= idx << (42 - 6 * i)
    return _assemble(df, ca, icao, me)


def build_airborne_pos(
    icao: int,
    lat: float,
    lon: float,
    alt_ft: int,
    fflag: bool = False,
    ca: int = 5,
    tc: int = 11,
    ss: int = 0,
    saf: int = 0,
    df: int = 17,
) -> bytes:
    dlat = 360.0 / 59.0 if fflag else 360.0 / 60.0
    lat_cpr = _cpr_frac(lat, dlat)
    nl = cpr_nl(lat)
    if fflag:
        dlon = 360.0 / max(nl - 1, 1)  # odd frames: NL-1 longitude zones
    else:
        dlon = 360.0 / nl  # even frames: NL longitude zones
    lon_cpr = _cpr_frac(lon, dlon)
    me = (
        (tc << 51)
        | (ss << 49)
        | (saf << 48)
        | (_altfield(alt_ft) << 36)
        | (int(fflag) << 34)
        | (lat_cpr << 17)
        | lon_cpr
    )
    return _assemble(df, ca, icao, me)


def build_velocity(
    icao: int,
    gs_kt: float,
    track_deg: float,
    vs_fpm: int = 0,
    subtype: int = 1,
    ca: int = 5,
    df: int = 17,
) -> bytes:
    tr = radians(track_deg)
    v_sn = gs_kt * cos(tr)  # north positive
    v_we = gs_kt * sin(tr)  # east positive
    ew_mag = int(round(abs(v_we))) + 1
    ns_mag = int(round(abs(v_sn))) + 1
    ew_mag = max(0, min(1023, ew_mag))
    ns_mag = max(0, min(1023, ns_mag))
    ew_sign = 1 if v_we < 0 else 0
    ns_sign = 1 if v_sn < 0 else 0
    if abs(vs_fpm) > 0:
        vr_mag = int(round(abs(vs_fpm) / 64.0)) + 1
        vr_mag = max(1, min(511, vr_mag))
        vr_sign = 1 if vs_fpm < 0 else 0
    else:
        vr_mag = 0
        vr_sign = 0
    me = (
        (19 << 51)
        | (subtype << 48)
        | (ew_sign << 42)
        | (ew_mag << 32)
        | (ns_sign << 31)
        | (ns_mag << 21)
        | (vr_sign << 19)
        | (vr_mag << 10)
    )
    return _assemble(df, ca, icao, me)
