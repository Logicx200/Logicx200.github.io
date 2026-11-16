#!/usr/bin/env python3
"""Command-line entry point for the ADS-B radar.

Examples
--------
    # Self-contained: demodulate the dongle directly with pyrtlsdr
    python run.py --source rtlsdr --lat 31.23 --lon 121.47

    # Use the rtl_adsb helper (lower CPU)
    python run.py --source rtl_adsb

    # Feed from a remote dump1090/readsb on the LAN
    python run.py --source network --host 192.168.1.20 --port-remote 30002

    # Demo with synthetic traffic (no hardware needed)
    python run.py --source sim
"""

from __future__ import annotations

import argparse


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="RTL-SDR V4 ADS-B 接收 + 雷达式航迹显示")
    p.add_argument("--config", default=None, help="配置文件路径（默认 config.json）")
    p.add_argument("--source", choices=["rtlsdr", "rtl_adsb", "network", "sim", "rtl_tcp", "transit_demo"], default=None)
    p.add_argument("--lat", type=float, default=None, help="接收站纬度（如 31.23）")
    p.add_argument("--lon", type=float, default=None, help="接收站经度（如 121.47）")
    p.add_argument("--range", type=float, default=None, dest="range_km", help="雷达半径 km")
    p.add_argument("--alt-m", type=float, default=None, dest="alt_m", help="接收站海拔（米，用于凌日/月仰角）")
    p.add_argument("--port", type=int, default=None, help="网页服务端口")
    p.add_argument("--host-bind", default=None, dest="host_bind", help="监听地址")
    p.add_argument("--gain", default=None, help="增益，如 auto 或 49.6")
    p.add_argument("--ppm", type=float, default=None, help="频率校正 ppm")
    p.add_argument("--device-index", type=int, default=None)
    p.add_argument("--rtl-adsb", default=None, help="rtl_adsb 可执行文件路径")
    p.add_argument("--host", default=None, help="dump1090/readsb 主机")
    p.add_argument("--port-remote", type=int, default=None, help="dump1090/readsb 端口")
    p.add_argument("--tcp-host", default=None, help="rtl_tcp 主机")
    p.add_argument("--tcp-port", type=int, default=None, help="rtl_tcp 端口")
    p.add_argument("--sim-n", type=int, default=None, help="仿真目标数量")
    p.add_argument("--sim-seed", type=int, default=None, help="仿真随机种子")
    p.add_argument("--sim-lat", type=float, default=None)
    p.add_argument("--sim-lon", type=float, default=None)
    return p


def main() -> None:
    from adsbradar.config import Config
    from adsbradar.server import run

    args = _build_parser().parse_args()
    cfg = Config.from_args(args)
    run(cfg)


if __name__ == "__main__":
    main()
