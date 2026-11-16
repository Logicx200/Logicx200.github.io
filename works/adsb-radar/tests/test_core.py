"""Core protocol tests against real, widely-cited ADS-B frames."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adsbradar import msgen  # noqa: E402
from adsbradar.cpr import airborne_global, airborne_local  # noqa: E402
from adsbradar.crc import icao_and_check  # noqa: E402
from adsbradar.decode import parse_frame  # noqa: E402

# Real captured frames (canonical examples used throughout the ADS-B literature).
EVEN = bytes.fromhex("8D40621D58C382D690C8AC2863A7")  # ICAO 40621D, airborne pos, even
IDENT = bytes.fromhex("8D4840D6202CC371C32CE0576098")  # ICAO 4840D6, callsign KLM1023


class TestCRC(unittest.TestCase):
    def test_icao_and_validity(self):
        self.assertEqual(icao_and_check(EVEN), ("40621D", True))
        self.assertEqual(icao_and_check(IDENT), ("4840D6", True))

    def test_corrupt_frame_rejected(self):
        bad = bytearray(EVEN)
        bad[-1] ^= 0x01
        _, ok = icao_and_check(bytes(bad))
        self.assertFalse(ok)


class TestDecode(unittest.TestCase):
    def test_callsign(self):
        m = parse_frame(IDENT)
        self.assertEqual(m["icao"], "4840D6")
        self.assertEqual(m["kind"], "ident")
        self.assertEqual(m["callsign"], "KLM1023")

    def test_airborne_position_fields(self):
        m = parse_frame(EVEN)
        self.assertEqual(m["icao"], "40621D")
        self.assertEqual(m["kind"], "airborne_pos")
        self.assertFalse(m["fflag"])
        self.assertEqual(m["alt_ft"], 38000)
        self.assertEqual(m["tc"], 11)


class TestRoundTrip(unittest.TestCase):
    def test_ident(self):
        f = msgen.build_ident(0x4840D6, "KLM1023")
        self.assertEqual(icao_and_check(f), ("4840D6", True))
        self.assertEqual(parse_frame(f)["callsign"], "KLM1023")

    def test_altitude(self):
        for alt in (0, 1000, 25000, 35000, 38000, 45000):
            f = msgen.build_airborne_pos(0xABCDEF, 31.23, 121.47, alt, fflag=False)
            self.assertEqual(parse_frame(f)["alt_ft"], alt, f"alt {alt}")

    def test_position_local_roundtrip(self):
        for lat, lon in [(31.23, 121.47), (-33.94, 151.18), (51.5, -0.12)]:
            for fflag in (False, True):
                f = msgen.build_airborne_pos(0xABCDEF, lat, lon, 35000, fflag=fflag)
                self.assertEqual(icao_and_check(f)[0], "ABCDEF")
                m = parse_frame(f)
                got = airborne_local(m["lat_cpr"], m["lon_cpr"], lat, lon, fflag)
                self.assertAlmostEqual(got[0], lat, places=3)
                self.assertAlmostEqual(got[1], lon, places=3)

    def test_position_global_roundtrip(self):
        for lat, lon in [(-40.2, 118.1), (29.0, -83.3), (16.7, 98.2), (-44.7, -160.4)]:
            fe = msgen.build_airborne_pos(0xABCDEF, lat, lon, 36000, fflag=False)
            fo = msgen.build_airborne_pos(0xABCDEF, lat, lon, 36000, fflag=True)
            me, mo = parse_frame(fe), parse_frame(fo)
            pos = airborne_global(
                me["lat_cpr"], me["lon_cpr"], mo["lat_cpr"], mo["lon_cpr"], True
            )
            self.assertIsNotNone(pos, f"global {lat},{lon}")
            self.assertAlmostEqual(pos[0], lat, places=2)
            self.assertAlmostEqual(pos[1], lon, places=2)

    def test_velocity_roundtrip(self):
        f = msgen.build_velocity(0xABCDEF, 450.0, 210.0, vs_fpm=-1024)
        self.assertEqual(icao_and_check(f)[0], "ABCDEF")
        m = parse_frame(f)
        self.assertEqual(m["kind"], "velocity")
        self.assertAlmostEqual(m["gs_kt"], 450.0, delta=1.5)
        self.assertAlmostEqual(m["track_deg"], 210.0, delta=1.0)
        self.assertAlmostEqual(m["vs_fpm"], -1024, delta=70)


if __name__ == "__main__":
    unittest.main(verbosity=2)
