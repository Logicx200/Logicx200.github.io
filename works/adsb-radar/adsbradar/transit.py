"""Sun/Moon transit prediction for ADS-B aircraft.

A "transit" happens when, seen from the receiver, an aircraft's line of sight
crosses the Sun or the Moon disc.  We predict it by extrapolating each
aircraft's current track/speed over a short horizon and searching for the
closest angular approach to the Sun/Moon centre.

The Sun/Moon position comes from the ``astral`` library (pure Python).  If
``astral`` is not installed the feature degrades gracefully and the radar keeps
working without it.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

SUN_RADIUS_DEG = 0.267
MOON_RADIUS_DEG = 0.260
# Report any predicted closest-approach closer than this (slightly wider than a
# disc so the operator also sees near-misses).
TRANSIT_THRESHOLD_DEG = 0.5

_KT_TO_MPS = 0.514444
_FPM_TO_MPS = 0.00508
_FT_TO_M = 0.3048


def _unit_vec(az_deg: float, el_deg: float) -> tuple[float, float, float]:
    az = math.radians(az_deg)
    el = math.radians(el_deg)
    ce = math.cos(el)
    return (ce * math.sin(az), ce * math.cos(az), math.sin(el))


def angular_distance_deg(az1: float, el1: float, az2: float, el2: float) -> float:
    x1, y1, z1 = _unit_vec(az1, el1)
    x2, y2, z2 = _unit_vec(az2, el2)
    dot = x1 * x2 + y1 * y2 + z1 * z2
    dot = max(-1.0, min(1.0, dot))
    return math.degrees(math.acos(dot))


def _enu_to_azel(north_m: float, east_m: float, up_m: float) -> tuple[float, float]:
    az = math.degrees(math.atan2(east_m, north_m)) % 360.0
    el = math.degrees(math.atan2(up_m, math.hypot(north_m, east_m)))
    return az, el


class TransitCalculator:
    """Computes Sun/Moon azimuth/elevation and predicts aircraft transits."""

    def __init__(self, lat: float | None, lon: float | None, alt_m: float = 0.0) -> None:
        self.lat = lat
        self.lon = lon
        self.alt_m = alt_m
        self.available = False
        self._observer = None
        self._sun_az = self._sun_el = None
        self._moon_az = self._moon_el = None
        self._cache_ts = 0.0
        self._cache_result: tuple[list[dict], dict] | None = None
        self._build_observer()

    def _build_observer(self) -> None:
        self.available = False
        self._observer = None
        if self.lat is None or self.lon is None:
            return
        try:
            from astral import Observer
            from astral.moon import azimuth as moon_azimuth, elevation as moon_elevation
            from astral.sun import azimuth as sun_azimuth, elevation as sun_elevation

            self._observer = Observer(latitude=self.lat, longitude=self.lon, elevation=self.alt_m)
            self._sun_az = sun_azimuth
            self._sun_el = sun_elevation
            self._moon_az = moon_azimuth
            self._moon_el = moon_elevation
            self.available = True
        except Exception:
            self._observer = None

    def set_location(self, lat: float | None, lon: float | None) -> None:
        if (lat, lon) == (self.lat, self.lon):
            return
        self.lat = lat
        self.lon = lon
        self._build_observer()

    def _sun_azel(self, dt: datetime) -> tuple[float, float]:
        return self._sun_az(self._observer, dt), self._sun_el(self._observer, dt)

    def _moon_azel(self, dt: datetime) -> tuple[float, float]:
        return self._moon_az(self._observer, dt), self._moon_el(self._observer, dt)

    def predict(
        self,
        aircraft: list[dict],
        now_ts: float,
        horizon_s: float = 600.0,
        step_s: float = 5.0,
    ) -> tuple[list[dict], dict]:
        """Return ``(transits, bodies)`` for the given aircraft snapshot.

        The result is cached for ~2s: the Sun/Moon move slowly and a 10-minute
        transit prediction does not need to be recomputed on every poll.
        """
        if self._cache_result is not None and now_ts - self._cache_ts < 2.0:
            return self._cache_result

        bodies = self._bodies(now_ts)
        if not self.available:
            result = ([], bodies)
        else:
            result = (self._predict(aircraft, now_ts, horizon_s, step_s), bodies)
        self._cache_ts = now_ts
        self._cache_result = result
        return result

    def _azel_at(self, body: str, now_dt: datetime, t: float) -> tuple[float, float]:
        dt = now_dt + timedelta(seconds=t)
        return self._sun_azel(dt) if body == "sun" else self._moon_azel(dt)

    def _predict(
        self,
        aircraft: list[dict],
        now_ts: float,
        horizon_s: float,
        step_s: float,
    ) -> list[dict]:
        now_dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)
        steps = int(horizon_s // step_s)
        sun_azel = [self._sun_azel(now_dt + timedelta(seconds=i * step_s)) for i in range(steps + 1)]
        moon_azel = [self._moon_azel(now_dt + timedelta(seconds=i * step_s)) for i in range(steps + 1)]

        transits: list[dict] = []
        for ac in aircraft:
            brg = ac.get("brg_deg")
            dist = ac.get("dist_km")
            alt_ft = ac.get("alt_ft")
            gs_kt = ac.get("gs_kt")
            trk = ac.get("track_deg")
            if None in (brg, dist, alt_ft, gs_kt, trk):
                continue

            north0 = dist * 1000.0 * math.cos(math.radians(brg))
            east0 = dist * 1000.0 * math.sin(math.radians(brg))
            up0 = alt_ft * _FT_TO_M - self.alt_m

            spd = gs_kt * _KT_TO_MPS
            vn = spd * math.cos(math.radians(trk))
            ve = spd * math.sin(math.radians(trk))
            vu = (ac.get("vs_fpm") or 0) * _FPM_TO_MPS

            def dist_at(t: float, baz: float, bel: float) -> float:
                az, el = _enu_to_azel(north0 + vn * t, east0 + ve * t, up0 + vu * t)
                return angular_distance_deg(az, el, baz, bel)

            for body, azel_list in (("sun", sun_azel), ("moon", moon_azel)):
                # coarse pass: find the closest grid point
                best_d = 1e9
                best_t = 0.0
                for i, (baz, bel) in enumerate(azel_list):
                    t = i * step_s
                    d = dist_at(t, baz, bel)
                    if d < best_d:
                        best_d, best_t = d, t
                # fine refinement around the coarse minimum (only for candidates)
                if best_d < 2.0:
                    lo = max(0.0, best_t - step_s)
                    hi = min(horizon_s, best_t + step_s)
                    fine = 1.0
                    t = lo
                    while t <= hi + 1e-9:
                        baz, bel = self._azel_at(body, now_dt, t)
                        d = dist_at(t, baz, bel)
                        if d < best_d:
                            best_d, best_t = d, t
                        t += fine
                if best_d < TRANSIT_THRESHOLD_DEG:
                    transits.append(
                        {
                            "icao": ac.get("icao"),
                            "callsign": ac.get("callsign"),
                            "body": body,
                            "dist_deg": round(best_d, 2),
                            "eta_s": round(best_t, 1),
                        }
                    )

        transits.sort(key=lambda x: (x["eta_s"], x["body"]))
        return transits

    def _bodies(self, now_ts: float) -> dict:
        if not self.available:
            return {"sun": None, "moon": None}
        dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)
        saz, sel = self._sun_azel(dt)
        maz, mel = self._moon_azel(dt)
        return {
            "sun": {"az": round(saz, 2), "el": round(sel, 2), "radius": SUN_RADIUS_DEG},
            "moon": {"az": round(maz, 2), "el": round(mel, 2), "radius": MOON_RADIUS_DEG},
        }
