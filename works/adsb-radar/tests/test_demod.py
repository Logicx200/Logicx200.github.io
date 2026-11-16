"""Demodulator tests.

The demodulator is a direct port of readsb/dump1090's ``demod_2400.c`` (2.4 MHz
path).  The slice/phase logic is verified here by decoding a synthesized signal
at a known-aligned phase; the preamble *detector* is verified to fire on the
preamble region.  (A bit-exact end-to-end synthetic round-trip is not asserted,
because the RTL-SDR's exact IF-filter pulse response — which the reference
coefficients are hand-tuned against — cannot be reproduced without hardware.)
"""

from __future__ import annotations

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adsbradar import msgen  # noqa: E402
from adsbradar.demod import Demodulator  # noqa: E402

SR = 2.4e6
OSR = 20


def rect_iq(frame: bytes, delay_us: float = 0.4167, pad: int = 300) -> np.ndarray:
    """Rectangular 0.5 us pulses at 20x, decimated to 2.4 MSps, as real IQ."""
    fs = SR * OSR
    us = fs / 1e6
    bits = [(b >> (7 - i)) & 1 for b in frame for i in range(8)]
    n = int(round((8.0 + len(bits) + delay_us) * us)) + pad * OSR
    m = np.zeros(n, dtype=np.float64)

    def pulse(t0, t1):
        a, b = int(t0 * us), int(t1 * us)
        m[a : min(b, n)] = 1.0

    d = delay_us
    for t0, t1 in ((0.0, 0.5), (1.0, 1.5), (3.5, 4.0), (4.5, 5.0)):
        pulse(d + t0, d + t1)
    for i, b in enumerate(bits):
        t0 = 8.0 + i
        pulse(d + t0, d + t0 + 0.5) if b else pulse(d + t0 + 0.5, d + t0 + 1.0)

    m = m[: n // OSR * OSR].reshape(-1, OSR).mean(axis=1)
    return m.astype(np.complex128)


class TestDemod(unittest.TestCase):
    def setUp(self):
        self.frame = msgen.build_airborne_pos(0xABCDEF, 31.23, 121.47, 35000, fflag=False)
        self.demod = Demodulator()

    def test_preamble_detection_finds_candidate(self):
        m = np.abs(rect_iq(self.frame))
        noise = float(np.median(m[::4]))
        cands = self.demod._candidates(m, noise)
        self.assertGreater(len(cands), 0)
        self.assertTrue(any(abs(int(c) - 0) <= 3 for c in cands), list(cands[:10]))

    def test_slice_decode_is_bit_perfect_at_alignment(self):
        m = np.abs(rect_iq(self.frame, delay_us=0.0))
        found = False
        for pa in range(-2, 3):
            for ph in (4, 5, 6, 7, 8):
                if self.demod._decode_phase(m, pa, ph) == self.frame:
                    found = True
        self.assertTrue(found, "no (pa, phase) alignment decodes the frame exactly")

    def test_feed_recovers_frame(self):
        # full pipeline (detect -> vectorised batch decode -> CRC) round-trip
        frames = self.demod.feed(rect_iq(self.frame, delay_us=0.4167))
        self.assertIn(self.frame, frames)


if __name__ == "__main__":
    unittest.main(verbosity=2)
