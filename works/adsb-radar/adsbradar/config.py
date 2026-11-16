"""Runtime configuration: defaults <- config.json <- command line."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields


@dataclass
class Config:
    source: str = "rtlsdr"           # rtlsdr | rtl_adsb | network | sim
    lat: float | None = None          # receiver latitude (degrees)
    lon: float | None = None          # receiver longitude (degrees)
    range_km: float = 250.0           # default radar radius
    max_range_km: float = 700.0       # sanity bound for position fixes
    alt_m: float = 0.0                # receiver altitude (meters) for transit/elevation
    host_bind: str = "0.0.0.0"        # web server bind (0.0.0.0 = LAN accessible)
    port: int = 8080                  # web server port
    # RTL-SDR
    gain: str | None = None           # 'auto' or numeric dB
    ppm: float = 0.0                  # tuner frequency correction
    device_index: int = 0
    sample_rate: float = 2.4e6
    center_freq: float = 1090e6
    rtl_adsb: str = "rtl_adsb"        # path/name of rtl_adsb executable
    # rtl_tcp (raw IQ over TCP; e.g. the Android "RTL-SDR Driver" app TCP mode)
    tcp_host: str = "127.0.0.1"
    tcp_port: int = 1234
    # remote dump1090/readsb
    host: str = "127.0.0.1"
    port_remote: int = 30002
    # simulator
    sim_n: int = 14
    sim_seed: int | None = None
    sim_lat: float | None = None
    sim_lon: float | None = None
    # misc
    config_path: str = "config.json"

    @classmethod
    def from_args(cls, args) -> "Config":
        cfg = cls()
        path = getattr(args, "config", None) or cls.config_path
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                for fld in fields(cls):
                    if fld.name in data:
                        setattr(cfg, fld.name, data[fld.name])
            except (OSError, ValueError):
                pass
        for fld in fields(cls):
            val = getattr(args, fld.name, None)
            if val is not None:
                setattr(cfg, fld.name, val)
        return cfg
