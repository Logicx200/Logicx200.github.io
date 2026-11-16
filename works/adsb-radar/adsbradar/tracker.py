"""Aircraft state tracking: CPR position assembly, trails, and lifetime."""

from __future__ import annotations

from .cpr import airborne_global, airborne_local, surface_local
from .geo import bearing_deg, haversine_km


class Aircraft:
    __slots__ = (
        "icao", "callsign", "lat", "lon", "alt_ft", "gs_kt", "track_deg",
        "vs_fpm", "on_ground", "last_seen", "first_seen", "last_pos_ts",
        "n_msgs", "n_pos", "trail", "even", "odd",
    )

    def __init__(self, icao: str) -> None:
        self.icao = icao
        self.callsign: str | None = None
        self.lat: float | None = None
        self.lon: float | None = None
        self.alt_ft: int | None = None
        self.gs_kt: float | None = None
        self.track_deg: float | None = None
        self.vs_fpm: int | None = None
        self.on_ground = False
        self.last_seen = 0.0
        self.first_seen = 0.0
        self.last_pos_ts = 0.0
        self.n_msgs = 0
        self.n_pos = 0
        self.trail: list[tuple[float, float, float]] = []
        self.even: tuple[float, float, float] | None = None
        self.odd: tuple[float, float, float] | None = None


class Tracker:
    def __init__(
        self,
        lat: float | None = None,
        lon: float | None = None,
        max_range_km: float = 700.0,
        trail_len: int = 48,
    ) -> None:
        self.lat = lat
        self.lon = lon
        self.max_range = max_range_km
        self.trail_len = trail_len
        self.trail_min_dt = 2.0
        self.aircraft: dict[str, Aircraft] = {}
        self.origin: tuple[float, float] | None = (lat, lon) if lat is not None else None
        self.n_msgs = 0
        self.n_pos = 0
        self.n_crc_bad = 0

    def center(self) -> tuple[float, float] | None:
        if self.lat is not None:
            return (self.lat, self.lon)
        return self.origin

    def update(self, msg: dict, ts: float) -> Aircraft | None:
        icao = msg.get("icao")
        if not icao:
            return None
        self.n_msgs += 1
        a = self.aircraft.get(icao)
        if a is None:
            a = Aircraft(icao)
            self.aircraft[icao] = a
        a.last_seen = ts
        if a.first_seen == 0.0:
            a.first_seen = ts

        kind = msg.get("kind")
        if kind == "ident":
            if msg.get("callsign"):
                a.callsign = msg["callsign"]
        elif kind == "airborne_pos":
            a.on_ground = False
            if msg.get("alt_ft") is not None:
                a.alt_ft = msg["alt_ft"]
            self._position(a, msg, ts, surface=False)
        elif kind == "surface_pos":
            a.on_ground = True
            self._position(a, msg, ts, surface=True)
        elif kind == "velocity":
            if msg.get("gs_kt") is not None:
                a.gs_kt = msg["gs_kt"]
            if msg.get("track_deg") is not None:
                a.track_deg = msg["track_deg"]
            if msg.get("vs_fpm") is not None:
                a.vs_fpm = msg["vs_fpm"]
        return a

    def _position(self, a: Aircraft, msg: dict, ts: float, surface: bool) -> None:
        fflag = bool(msg["fflag"])
        lat_cpr = msg["lat_cpr"]
        lon_cpr = msg["lon_cpr"]

        pos: tuple[float, float] | None = None
        if not surface:
            if fflag:
                a.odd = (lat_cpr, lon_cpr, ts)
            else:
                a.even = (lat_cpr, lon_cpr, ts)
            if a.even is not None and a.odd is not None:
                pos = airborne_global(
                    a.even[0], a.even[1], a.odd[0], a.odd[1], a.even[2] >= a.odd[2]
                )

        if pos is None:
            ref_lat = self.lat if self.lat is not None else a.lat
            ref_lon = self.lon if self.lon is not None else a.lon
            if ref_lat is not None and ref_lon is not None:
                try:
                    dec = airborne_local if not surface else surface_local
                    pos = dec(lat_cpr, lon_cpr, ref_lat, ref_lon, fflag)
                except (ValueError, ZeroDivisionError):
                    pos = None

        if pos is None:
            return
        lat, lon = pos

        if self.lat is not None and haversine_km(self.lat, self.lon, lat, lon) > self.max_range:
            return
        if a.lat is not None:
            d = haversine_km(a.lat, a.lon, lat, lon)
            dt = ts - a.last_pos_ts
            if dt > 0 and d / dt > 2500.0:  # reject > 9000 km/h decode errors
                return

        a.lat = lat
        a.lon = lon
        a.last_pos_ts = ts
        a.n_pos += 1
        self.n_pos += 1

        if self.lat is None and self.origin is None:
            self.origin = (lat, lon)

        if not a.trail or (ts - a.trail[-1][0]) >= self.trail_min_dt:
            a.trail.append((ts, lat, lon))
            if len(a.trail) > self.trail_len:
                a.trail.pop(0)

    def expire(self, now: float, ttl: float = 60.0) -> int:
        dead = [k for k, a in self.aircraft.items() if now - a.last_seen > ttl]
        for k in dead:
            del self.aircraft[k]
        return len(dead)

    def snapshot(self, now: float) -> list[dict]:
        cx, cy = (None, None)
        center = self.center()
        if center is not None:
            cx, cy = center
        out: list[dict] = []
        for a in self.aircraft.values():
            d = brg = None
            if a.lat is not None and cx is not None:
                d = haversine_km(cx, cy, a.lat, a.lon)
                brg = bearing_deg(cx, cy, a.lat, a.lon)
            out.append(
                {
                    "icao": a.icao,
                    "callsign": a.callsign,
                    "lat": a.lat,
                    "lon": a.lon,
                    "alt_ft": a.alt_ft,
                    "gs_kt": a.gs_kt,
                    "track_deg": a.track_deg,
                    "vs_fpm": a.vs_fpm,
                    "on_ground": a.on_ground,
                    "dist_km": d,
                    "brg_deg": brg,
                    "age_s": round(now - a.last_seen, 2),
                    "seen_s": round(now - a.first_seen, 1),
                    "trail": [[t[2], t[1], round(t[0], 3)] for t in a.trail],
                    "n_pos": a.n_pos,
                    "n_msgs": a.n_msgs,
                }
            )
        out.sort(key=lambda x: (x["dist_km"] is None, x["dist_km"] if x["dist_km"] is not None else 0.0))
        return out
