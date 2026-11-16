"""Mode S 24-bit CRC (parity) generation and verification.

Generator polynomial (Annex 10 / ICAO)::

    G(x) = x^24 + x^23 + x^22 + x^21 + x^20 + x^19 + x^18 + x^17 + x^16
         + x^15 + x^14 + x^13 + x^12 + x^10 + x^3 + 1
         = 0x1FFF409

The parity (PI/AP) field is the remainder of polynomial division of the data
bits with 24 appended zero bits.  For DF17/DF18 (and DF11 all-call replies) the
transmitted parity has the 24-bit ICAO address XORed into it.
"""

from __future__ import annotations

POLY = 0x1FFF409  # 25-bit generator


def crc24(data: int, n_bits: int) -> int:
    """Remainder of polynomial division of ``data`` (``n_bits`` MSB-first).

    ``data`` is treated as an ``n_bits``-long bit string; the returned value is
    the 24-bit remainder, equivalent to appending 24 zero bits and dividing by
    the generator polynomial.
    """
    reg = data << 24  # append the 24 "zero" parity bits
    top = n_bits + 24 - 1
    for i in range(n_bits):
        if (reg >> (top - i)) & 1:
            reg ^= POLY << (n_bits - 1 - i)
    return reg & 0xFFFFFF


def crc24_bytes(data: bytes) -> int:
    """Remainder over a whole byte string (MSB-first across bytes)."""
    n = len(data) * 8
    return crc24(int.from_bytes(data, "big"), n)


def icao_and_check(frame: bytes) -> tuple[str | None, bool]:
    """Extract ICAO address and CRC-validity flag from a 7/14-byte Mode S frame.

    For DF17/18 (extended squitter) a frame is valid when the CRC syndrome
    ``crc(data_bits) ^ parity == 0``; the ICAO address is read directly from
    bits 9-32.  Returns ``(icao_hex, ok)``; ``icao_hex`` is ``None`` when the
    frame type does not carry an address.
    """
    if len(frame) == 14:
        df = frame[0] >> 3
        data = int.from_bytes(frame[:11], "big")
        pi = int.from_bytes(frame[11:14], "big")
        ok = (crc24(data, 88) ^ pi) == 0
        if df in (17, 18):
            icao = f"{int.from_bytes(frame[1:4], 'big'):06X}"
            return icao, ok
        return None, ok
    if len(frame) == 7:
        df = frame[0] >> 3
        data = int.from_bytes(frame[:4], "big")
        pi = int.from_bytes(frame[4:7], "big")
        ok = (crc24(data, 32) ^ pi) == 0
        if df == 11:  # all-call reply carries the ICAO
            return f"{int.from_bytes(frame[1:4], 'big'):06X}", ok
        return None, ok
    return None, False
