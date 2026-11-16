#!/usr/bin/env python3
"""接收链路自检：抓取几秒 1090 MHz 数据并统计解调结果。

用来确认「驱动 → 调谐器 → 采样 → 解调 → CRC」整条链路是否工作，以及
当前天线/增益下能否收到 ADS-B 报文。

用法：
    python tools/test_receiver.py --gain 40.2 --seconds 6

输出里最重要的是：
    CRC-valid N  —— N > 0 就说明已经收到真实 ADS-B 报文；
    若 N == 0 且 peaks 很小，通常是天线还没调成 1090 MHz 或位置遮挡。
"""

from __future__ import annotations

import argparse
import time

import numpy as np


def main() -> int:
    ap = argparse.ArgumentParser(description="RTL-SDR 接收自检")
    ap.add_argument("--gain", default="40.2", help="增益 dB（默认 40.2，可用 auto / 49.6 等）")
    ap.add_argument("--seconds", type=float, default=6.0, help="抓取时长（秒）")
    ap.add_argument("--freq", type=float, default=1090e6)
    args = ap.parse_args()

    try:
        from rtlsdr import RtlSdr
    except ImportError:
        print("未安装 pyrtlsdr：pip install pyrtlsdr pyrtlsdrlib")
        return 1

    import sys
    sys.path.insert(0, ".")
    from adsbradar.demod import Demodulator
    from adsbradar.crc import icao_and_check

    s = RtlSdr()
    print(f"tuner: {s.get_tuner_type()}  (5=R820T/2, V4 的 R828D 常显示为 5)")
    s.sample_rate = 2.4e6
    s.center_freq = args.freq
    try:
        s.gain = float(args.gain) if args.gain.lower() != "auto" else "auto"
    except ValueError:
        s.gain = "auto"
    print(f"gain={s.gain}  freq={args.freq/1e6:.1f}MHz  rate={s.sample_rate/1e6:.1f}MSps")
    time.sleep(0.4)

    d = Demodulator()
    raw = 0
    valid = 0
    peak = 0.0
    t0 = time.time()
    while time.time() - t0 < args.seconds:
        x = np.asarray(s.read_samples(262144))
        peak = max(peak, float(np.abs(x).max()))
        for f in d.feed(x):
            raw += 1
            _, ok = icao_and_check(f)
            valid += 1 if ok else 0
    s.close()

    print(f"抓取 {args.seconds:.0f}s: 前导码 {raw}   CRC-valid {valid}   峰值 {peak:.2f}")
    if valid > 0:
        print("OK：已收到真实 ADS-B 报文。可运行 python run.py --source rtlsdr")
    else:
        print("没收到报文。检查：1) 天线每臂 6.9cm、竖直、靠窗  2) --gain 调到 40~49.6  3) 高空无遮挡")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
