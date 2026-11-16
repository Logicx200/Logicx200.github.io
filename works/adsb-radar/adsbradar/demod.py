"""1090 MHz Mode S demodulator — a Python port of readsb/dump1090's
``demod_2400.c`` (2.4 MHz path), which is the battle-tested reference.

The magnitude envelope is sliced with five DC-balanced correlation functions,
each corresponding to a sub-sample phase offset (1/5 sample granularity).  The
preamble is found with a cheap relative-amplitude pre-check plus a local
noise-referenced threshold; then every viable phase is decoded and the CRC
chooses the winner, so false preambles and wrong phases are rejected naturally.

Only long (112-bit) frames — DF17/DF18 extended squitters, which is what an
ADS-B radar display needs — are returned.  Chunks are processed independently;
a frame straddling a chunk boundary is lost (about 0.1% of traffic at the
default 262144-sample chunk size).
"""

from __future__ import annotations

import numpy as np

from .crc import icao_and_check

SAMPLE_RATE = 2.4e6
PREAMBLE_THRESHOLD = 5.0  # relative to the local noise window (readsb default)
MAX_CANDIDATES = 2000  # safety cap against overload/clipping flooding the loop

_SHORT_DFS = {0, 4, 5, 11}
# Only ADS-B extended squitters (DF17/18) are fully decoded; every other DF is
# rejected after its first byte.  This keeps the Python decode loop real-time:
# ~94% of noise candidates have a spurious DF and are dropped cheaply.
_LONG_DFS = {17, 18}


def _s0(m, p):
    return 18.0 * m[p] - 15.0 * m[p + 1] - 3.0 * m[p + 2]


def _s1(m, p):
    return 14.0 * m[p] - 5.0 * m[p + 1] - 9.0 * m[p + 2]


def _s2(m, p):
    return 16.0 * m[p] + 5.0 * m[p + 1] - 20.0 * m[p + 2]


def _s3(m, p):
    return 7.0 * m[p] + 11.0 * m[p + 1] - 18.0 * m[p + 2]


def _s4(m, p):
    return 4.0 * m[p] + 15.0 * m[p + 1] - 20.0 * m[p + 2] + 1.0 * m[p + 3]


_SLICE_FNS = (_s0, _s1, _s2, _s3, _s4)

# For each phase: (slice_fn_index, sample_offset) for bits MSB..LSB.
_SLICE_TABLE = (
    ((0, 0), (2, 2), (4, 4), (1, 7), (3, 9), (0, 12), (2, 14), (4, 16)),
    ((1, 0), (3, 2), (0, 5), (2, 7), (4, 9), (1, 12), (3, 14), (0, 17)),
    ((2, 0), (4, 2), (1, 5), (3, 7), (0, 10), (2, 12), (4, 14), (1, 17)),
    ((3, 0), (0, 3), (2, 5), (4, 7), (1, 10), (3, 12), (0, 15), (2, 17)),
    ((4, 0), (1, 3), (3, 5), (0, 8), (2, 10), (4, 12), (1, 15), (3, 17)),
)
_ADVANCE = (19, 19, 19, 19, 20)
_NEXT_PHASE = (1, 2, 3, 4, 0)

# Coefficients of the five DC-balanced slice correlation functions.
_COEFFS = ((18.0, -15.0, -3.0), (14.0, -5.0, -9.0), (16.0, 5.0, -20.0),
           (7.0, 11.0, -18.0), (4.0, 15.0, -20.0, 1.0))

# Precomputed per-try_phase plan: for each of the 112 bits, (fn_idx, sample
# offset from the candidate start) so the decode can run vectorised.
_PLAN: dict[int, list[tuple[int, int]]] = {}
_MAX_OFF = 0
for _tp in (4, 5, 6, 7, 8):
    _p = 19 + _tp // 5
    _ph = _tp % 5
    _plan: list[tuple[int, int]] = []
    for _ in range(14):
        for _fn, _off in _SLICE_TABLE[_ph]:
            _plan.append((_fn, _p + _off))
        _p += _ADVANCE[_ph]
        _ph = _NEXT_PHASE[_ph]
    _PLAN[_tp] = _plan
    _MAX_OFF = max(_MAX_OFF, max(off for _, off in _plan))


class Demodulator:
    def __init__(self) -> None:
        self._noise = 0.0

    @property
    def noise_floor(self) -> float:
        return self._noise

    def feed(self, iq: np.ndarray) -> list[bytes]:
        iq = np.asarray(iq)
        if not np.iscomplexobj(iq):
            raise TypeError("feed() expects complex IQ samples")
        m = np.abs(iq).astype(np.float64)
        n = m.size
        if n < 512:
            return []

        med = float(np.median(m[::4]))
        self._noise = med if self._noise == 0.0 else 0.9 * self._noise + 0.1 * med
        noise = max(self._noise, 1e-12)

        cand = self._candidates(m, noise)[:MAX_CANDIDATES]
        # keep only candidates whose full 112-bit frame fits in this chunk
        cand = cand[cand < n - _MAX_OFF - 4]
        return self._decode_batch(m, cand)

    @staticmethod
    def _candidates(m: np.ndarray, noise: float) -> np.ndarray:
        """Vectorised preamble pre-check + local noise threshold."""
        n = m.size
        K = n - 20
        if K <= 0:
            return np.array([], dtype=np.int64)

        # relative shape check (readsb pre-check)
        pre = (m[1 : 1 + K] > m[7 : 7 + K]) & (m[12 : 12 + K] > m[14 : 14 + K]) & (
            m[12 : 12 + K] > m[15 : 15 + K]
        )

        # soft absolute gate: the outer two pulses must sit above the noise floor
        thr_abs = noise * 1.6
        abs_ok = (m[1 : 1 + K] > thr_abs) & (m[12 : 12 + K] > thr_abs)

        d23 = m[2 : 2 + K] - m[3 : 3 + K]
        s14 = m[1 : 1 + K] + m[4 : 4 + K]
        d1011 = m[10 : 10 + K] - m[11 : 11 + K]
        common = s14 - d23 + m[9 : 9 + K] + m[12 : 12 + K]
        base = m[5 : 5 + K] + m[8 : 8 + K] + m[16 : 16 + K] + m[17 : 17 + K] + m[18 : 18 + K]
        ref = base * (PREAMBLE_THRESHOLD / 32.0)

        hit = pre & abs_ok & (
            (common - d1011 >= ref)
            | (common + d1011 >= ref)
            | (s14 + 2.0 * d23 + d1011 + m[12 : 12 + K] >= ref)
        )
        return np.nonzero(hit)[0]

    def _decode_batch(self, m: np.ndarray, pa_arr: np.ndarray) -> list[bytes]:
        """Vectorised decode of every candidate across the five phases.

        All 112 bits for all candidates are sliced with numpy array ops, then
        only DF17/18 frames are CRC-checked (in a short Python loop over the
        survivors).  A candidate that validates in one phase is not retried.
        """
        N = pa_arr.size
        if N == 0:
            return []
        done = np.zeros(N, dtype=bool)
        frames: list[bytes] = []
        for try_phase in (4, 5, 6, 7, 8):
            idxs = np.nonzero(~done)[0]
            if idxs.size == 0:
                break
            pa_sub = pa_arr[idxs]
            bits = np.zeros((idxs.size, 112), dtype=np.uint8)
            for i, (fn_idx, off) in enumerate(_PLAN[try_phase]):
                c = _COEFFS[fn_idx]
                idx = pa_sub + off
                val = c[0] * m[idx]
                for k in range(1, len(c)):
                    val += c[k] * m[idx + k]
                bits[:, i] = val > 0.0
            byts = np.packbits(bits, axis=1, bitorder="big")  # (M, 14) uint8
            df = byts[:, 0] >> 3
            for j in np.nonzero((df == 17) | (df == 18))[0]:
                msg = bytes(byts[j])
                _, ok = icao_and_check(msg)
                if ok:
                    frames.append(msg)
                    done[idxs[j]] = True
        return frames

    def _decode_phase(self, m: np.ndarray, pa: int, try_phase: int) -> bytes | None:
        n = m.size
        p = pa + 19 + try_phase // 5
        phase = try_phase % 5

        out = bytearray()
        for _ in range(14):  # long frame; short frames are skipped below if DF doesn't fit
            b = 0
            for bit, (fn_idx, off) in enumerate(_SLICE_TABLE[phase]):
                idx = p + off
                if idx + 3 >= n:
                    return None
                if _SLICE_FNS[fn_idx](m, idx) > 0.0:
                    b |= 0x80 >> bit
            out.append(b)
            if len(out) == 1:
                df = out[0] >> 3
                if df in _SHORT_DFS:
                    # only long frames are of interest; still consume, then return None
                    nbytes = 7
                elif df in _LONG_DFS:
                    nbytes = 14
                else:
                    return None
            if len(out) == nbytes:
                break
            p += _ADVANCE[phase]
            phase = _NEXT_PHASE[phase]

        if len(out) != 14:
            return None
        msg = bytes(out)
        _, ok = icao_and_check(msg)
        return msg if ok else None


def demodulate(iq: np.ndarray) -> list[bytes]:
    return Demodulator().feed(iq)
