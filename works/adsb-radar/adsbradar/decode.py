"""Mode S (ADS-B) message parsing.

Turns a raw 7/14-byte frame into a small dict of typed fields.  Only the
1090ES messages an ADS-B radar display actually needs are decoded: aircraft
identification (DF17 TC 1-4), airborne position (TC 9-18), surface position
(TC 5-8), and velocity (TC 19).  DF18 (TIS-B) is accepted with the same layout.
"""

from __future__ import annotations

from math import atan2, degrees, sqrt

# 6-bit character set used by the callsign / ident field (ICAO Annex 10).
CHARSET = "#ABCDEFGHIJKLMNOPQRSTUVWXYZ#####_###############0123456789######"


def _bits(me: int, p1: int, n: int) -> int:
    """Extract ``n`` bits starting at 1-indexed position ``p1`` (MSB first)."""
    shift = 56 - (p1 + n - 1)
    return (me >> shift) & ((1 << n) - 1)


def _signed(v: int, bits: int) -> int:
    if v >= (1 << (bits - 1)):
        v -= 1 << bits
    return v


def _callsign(me: int) -> str:
    chars = [_bits(me, 9 + 6 * i, 6) for i in range(8)]
    out = "".join(CHARSET[c] if c < len(CHARSET) else " " for c in chars)
    return out.rstrip("_# ")


_MOV_LB = [2, 9, 13, 39, 94, 109, 124]
_KTS_LB = [0.125, 1, 2, 15, 70, 100, 175]
_STEP = [0.125, 0.25, 0.5, 1, 2, 5]


def _decode_movement(mov: int) -> float | None:
    if mov == 0 or mov > 124:
        return None
    if mov == 1:
        return 0.0
    if mov == 124:
        return 175.0
    for i, lb in enumerate(_MOV_LB):
        if lb > mov:
            return _KTS_LB[i - 1] + (mov - _MOV_LB[i - 1]) * _STEP[i - 1]
    return None


def _gray2int(n: int) -> int:
    n ^= n >> 8
    n ^= n >> 4
    n ^= n >> 2
    n ^= n >> 1
    return n


def _altcode_to_altitude(ac: int) -> int | None:
    """Decode a 13-bit Mode S altitude code to feet (``None`` if unknown)."""
    if ac == 0:
        return None
    m_bit = (ac >> 6) & 0x1
    q_bit = (ac >> 4) & 0x1
    if m_bit == 0 and q_bit == 1:  # 25 ft interval, linear
        n = ((ac >> 2) & 0x7E0) | ((ac >> 1) & 0x10) | (ac & 0xF)
        return n * 25 - 1000
    if m_bit == 0 and q_bit == 0:  # 100 ft interval, Gillham code
        def b(pos: int) -> int:
            return (ac >> (12 - pos)) & 0x1

        c1, a1, c2, a2, c4, a4 = b(0), b(1), b(2), b(3), b(4), b(5)
        b1, b2, d2, b4, d4 = b(7), b(9), b(10), b(11), b(12)
        gc500 = (d2 << 7) | (d4 << 6) | (a1 << 5) | (a2 << 4) | (a4 << 3) | (b1 << 2) | (b2 << 1) | b4
        gc100 = (c1 << 2) | (c2 << 1) | c4
        n500 = _gray2int(gc500)
        n100 = _gray2int(gc100)
        if n100 in (0, 5, 6):
            return None
        if n100 == 7:
            n100 = 5
        if n500 % 2:
            n100 = 6 - n100
        return n500 * 500 + n100 * 100 - 1300
    return None


def _altitude(ac12: int) -> int | None:
    # The 12-bit AC field expands to a 13-bit altcode (a zero M bit is
    # inserted), which the standard altitude decoder then consumes.
    altcode = ((ac12 >> 6) << 7) | (ac12 & 0x3F)
    return _altcode_to_altitude(altcode)


def parse_frame(frame: bytes) -> dict | None:
    """Parse a 7-byte (short) or 14-byte (long) frame into a field dict.

    Returns ``None`` if the frame is too short or an unsupported format.
    """
    if len(frame) == 7:
        return _parse_short(frame)
    if len(frame) == 14:
        return _parse_long(frame)
    return None


def _parse_short(frame: bytes) -> dict:
    df = frame[0] >> 3
    return {"df": df, "kind": "other"}


def _parse_long(frame: bytes) -> dict:
    df = frame[0] >> 3
    ca = frame[0] & 0x07
    icao = f"{int.from_bytes(frame[1:4], 'big'):06X}"
    me = int.from_bytes(frame[4:11], "big")
    tc = me >> 51

    out: dict = {"df": df, "ca": ca, "icao": icao, "tc": tc}

    if 1 <= tc <= 4:
        out["kind"] = "ident"
        out["callsign"] = _callsign(me)
        return out

    if 5 <= tc <= 8:
        out["kind"] = "surface_pos"
        out["on_ground"] = True
        mov = _bits(me, 6, 7)
        track_status = _bits(me, 13, 1)
        track_raw = _bits(me, 14, 7)
        fflag = bool(_bits(me, 22, 1))
        out["fflag"] = fflag
        out["lat_cpr"] = _bits(me, 23, 17) / 131072.0
        out["lon_cpr"] = _bits(me, 40, 17) / 131072.0
        gs = _decode_movement(mov)
        if gs is not None:
            out["gs_kt"] = gs
        if track_status:
            out["track_deg"] = round(track_raw * 360.0 / 128.0, 1)
        out["alt_ft"] = None
        return out

    if 9 <= tc <= 18:
        out["kind"] = "airborne_pos"
        out["ss"] = _bits(me, 6, 2)
        out["saf"] = _bits(me, 8, 1)
        altfield = _bits(me, 9, 12)
        out["alt_ft"] = _altitude(altfield)
        out["t"] = _bits(me, 21, 1)
        fflag = bool(_bits(me, 22, 1))
        out["fflag"] = fflag
        out["lat_cpr"] = _bits(me, 23, 17) / 131072.0
        out["lon_cpr"] = _bits(me, 40, 17) / 131072.0
        return out

    if tc == 19:
        out["kind"] = "velocity"
        st = _bits(me, 6, 3)
        out["subtype"] = st
        if st in (1, 2):
            ew_sign = _bits(me, 14, 1)
            ew_mag = _bits(me, 15, 10)
            ns_sign = _bits(me, 25, 1)
            ns_mag = _bits(me, 26, 10)
            if ew_mag and ns_mag:
                v_ew = (ew_mag - 1) * (4 if st == 2 else 1)
                v_ns = (ns_mag - 1) * (4 if st == 2 else 1)
                v_we = -v_ew if ew_sign else v_ew
                v_sn = -v_ns if ns_sign else v_ns
                out["gs_kt"] = round(sqrt(v_we * v_we + v_sn * v_sn), 1)
                out["track_deg"] = round((degrees(atan2(v_we, v_sn)) + 360.0) % 360.0, 1)
        elif st in (3, 4):
            hdg_status = _bits(me, 14, 1)
            hdg_raw = _bits(me, 15, 10)
            as_mag = _bits(me, 26, 10)
            if hdg_status:
                out["track_deg"] = round(hdg_raw / 1024.0 * 360.0, 1)
            if as_mag:
                out["tas_kt"] = (as_mag - 1) * (4 if st == 4 else 1)
        vr_sign = _bits(me, 37, 1)
        vr_mag = _bits(me, 38, 9)
        if vr_mag:
            vrt = (vr_mag - 1) * 64
            out["vs_fpm"] = -vrt if vr_sign else vrt
        return out

    if tc == 29 or (tc == 31 and df == 17):
        out["kind"] = "status"
        return out

    out["kind"] = "other"
    return out
