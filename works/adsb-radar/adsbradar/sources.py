"""Data sources: each yields raw 7/14-byte Mode S frames.

* ``rtlsdr``    — direct IQ demodulation with pyrtlsdr (self-contained).
* ``rtl_adsb``  — the ``rtl_adsb`` helper from the rtl-sdr tools (low CPU).
* ``network``   — a remote dump1090/readsb: AVR (30002), SBS (30003), Beast (30005).
* ``sim``       — synthetic traffic for demos and end-to-end tests.
"""

from __future__ import annotations

import queue
import subprocess
import threading
import time
from collections.abc import Iterator

from . import msgen
from .demod import Demodulator
from .geo import offset

# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

_AIRLINES = ("CCA", "CES", "CSN", "CAL", "UAL", "DAL", "KLM", "BAW", "SIA", "THY", "ANA", "JAL")


class _SimAircraft:
    __slots__ = ("icao", "callsign", "lat0", "lon0", "hdg", "gs_kt", "alt_ft", "phase", "t_next", "_rlat", "_rlon")

    def __init__(self, icao, callsign, lat0, lon0, hdg, gs_kt, alt_ft):
        self.icao = icao
        self.callsign = callsign
        self.lat0 = lat0
        self.lon0 = lon0
        self.hdg = hdg
        self.gs_kt = gs_kt
        self.alt_ft = alt_ft
        self.phase = 0
        self.t_next = 0.0

    _DELTAS = (8.0, 0.55, 0.55, 1.1)

    def schedule_next(self):
        self.phase = (self.phase + 1) % 4
        self.t_next += self._DELTAS[self.phase]

    def position(self, now, t0):
        elapsed = now - t0
        dist = self.gs_kt * 1.852 * elapsed / 3600.0
        return offset(self.lat0, self.lon0, dist, self.hdg)

    def next_frame(self, now, t0):
        lat, lon = self.position(now, t0)
        icao = int(self.icao, 16)
        if self.phase == 0:
            frame = msgen.build_ident(icao, self.callsign)
        elif self.phase in (1, 2):
            frame = msgen.build_airborne_pos(icao, lat, lon, self.alt_ft, fflag=(self.phase == 2))
        else:
            frame = msgen.build_velocity(icao, self.gs_kt, self.hdg, vs_fpm=0)
        return frame


def sim_source(cfg) -> Iterator[bytes]:
    import random

    center_lat = getattr(cfg, "sim_lat", None) or getattr(cfg, "lat", None) or 31.23
    center_lon = getattr(cfg, "sim_lon", None) or getattr(cfg, "lon", None) or 121.47
    rng = random.Random(getattr(cfg, "sim_seed", None))
    n = getattr(cfg, "sim_n", 14)

    acs = []
    for i in range(n):
        icao = f"{rng.randrange(0, 0xFFFFFF):06X}"
        cs = rng.choice(_AIRLINES) + f"{rng.randrange(100, 9999):04d}"
        d = rng.uniform(12.0, 260.0)
        brg = rng.uniform(0.0, 360.0)
        lat, lon = offset(center_lat, center_lon, d, brg)
        hdg = rng.uniform(0.0, 360.0)
        gs = rng.uniform(170.0, 470.0)
        alt = rng.choice([24000, 30000, 33000, 35000, 37000, 39000, 41000])
        ac = _SimAircraft(icao, cs, lat, lon, hdg, gs, alt)
        ac.t_next = time.monotonic() + rng.uniform(0.0, 2.0)
        acs.append(ac)

    t0 = time.monotonic()
    while True:
        now = time.monotonic()
        for ac in acs:
            while ac.t_next <= now:
                yield ac.next_frame(now, t0)
                ac.schedule_next()
        time.sleep(0.02)


def transit_demo_source(cfg) -> Iterator[bytes]:
    """Synthetic aircraft aligned with the Sun/Moon to demo the transit
    predictor.  Clearly-labelled test traffic (``sim``), not real data."""
    import math as _math

    from .transit import TransitCalculator

    center_lat = getattr(cfg, "sim_lat", None) or getattr(cfg, "lat", None) or 37.72
    center_lon = getattr(cfg, "sim_lon", None) or getattr(cfg, "lon", None) or 112.66
    alt_m = getattr(cfg, "alt_m", 800.0)

    tc = TransitCalculator(center_lat, center_lon, alt_m)
    bodies = tc._bodies(time.time())
    moon = bodies.get("moon") or {}
    maz = moon.get("az", 90.0)
    mel = moon.get("el", 20.0)

    def align_dist(alt_ft: float) -> float:
        up_m = alt_ft * 0.3048 - alt_m
        if mel <= 0:
            return 24.0
        return max(5.0, up_m / _math.tan(_math.radians(mel)) / 1000.0)

    acs: list[_SimAircraft] = []

    def add(icao: str, cs: str, brg: float, dist_km: float, hdg: float, gs: float, alt: float) -> None:
        lat, lon = offset(center_lat, center_lon, dist_km, brg)
        ac = _SimAircraft(icao, cs, lat, lon, hdg, gs, alt)
        ac._rlat, ac._rlon = lat, lon  # saved for the periodic rewind
        acs.append(ac)

    # Lunar-transit demo fleet: one parked on the disc, two inbound, one near-miss.
    d0 = align_dist(30000.0)
    add("780101", "TST101", maz, d0 * 3.0, (maz + 180.0) % 360.0, 420.0, 30000.0)   # transit in a few min
    add("780102", "TST202", maz, d0, (maz + 90.0) % 360.0, 0.0, 30000.0)            # parked on the disc
    add("780103", "TST303", (maz - 12.0) % 360.0, d0 * 1.6, maz, 380.0, 34000.0)    # inbound from the side
    add("780104", "TST404", (maz + 20.0) % 360.0, d0 * 0.7, (maz + 90.0) % 360.0, 260.0, 26000.0)  # near miss
    # a couple of ordinary aircraft for context
    add("780105", "TST505", (maz + 120.0) % 360.0, 80.0, 0.0, 400.0, 36000.0)
    add("780106", "TST606", (maz - 90.0) % 360.0, 120.0, 90.0, 380.0, 32000.0)

    for ac in acs:
        ac.t_next = time.monotonic() + 0.1
    t0 = time.monotonic()
    last_rewind = t0
    while True:
        now = time.monotonic()
        # periodically rewind so the transit demo keeps showing activity
        if now - last_rewind > 180.0:
            for ac in acs:
                ac.lat0, ac.lon0 = ac._rlat, ac._rlon
            t0 = now
            last_rewind = now
        for ac in acs:
            while ac.t_next <= now:
                yield ac.next_frame(now, t0)
                ac.schedule_next()
        time.sleep(0.02)


# ---------------------------------------------------------------------------
# rtl_adsb helper (subprocess)
# ---------------------------------------------------------------------------


def rtl_adsb_source(cfg) -> Iterator[bytes]:
    exe = getattr(cfg, "rtl_adsb", "rtl_adsb")
    args = [exe, "-s", "2400000", "-f", "1090000000"]
    gain = getattr(cfg, "gain", None)
    if gain not in (None, "", "auto"):
        args += ["-g", str(gain)]
    if getattr(cfg, "ppm", None):
        args += ["-p", str(cfg.ppm)]
    proc = subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1
    )
    try:
        for line in proc.stdout:
            line = line.strip()
            hexes = "".join(c for c in line if c in "0123456789abcdefABCDEF")
            if len(hexes) not in (14, 28):
                continue
            try:
                frame = bytes.fromhex(hexes)
            except ValueError:
                continue
            yield frame
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


# ---------------------------------------------------------------------------
# pyrtlsdr direct demodulation
# ---------------------------------------------------------------------------

_READ_SAMPLES = 262144


def rtlsdr_source(cfg, radio=None) -> Iterator[bytes]:
    import numpy as np

    def _apply_gain(sdr, value):
        try:
            if str(value).lower() == "auto":
                sdr.gain = "auto"
            else:
                sdr.gain = float(value)
            return sdr.gain
        except Exception:
            return None

    try:
        from rtlsdr import RtlSdr  # works on Windows/macOS via pyrtlsdrlib
    except Exception:
        try:
            from .librtlsdr import RTLSDR as RtlSdr  # minimal ctypes fallback
        except Exception as e:
            if radio is not None:
                radio.update(connected=False, error=f"无法加载 librtlsdr：{e}")
            raise RuntimeError(f"无法加载 librtlsdr：{e}（需安装 pyrtlsdr 或 librtlsdr）") from e

    try:
        sdr = RtlSdr(getattr(cfg, "device_index", 0))
    except Exception as e:
        if radio is not None:
            radio.update(connected=False, error=f"打不开接收棒：{e}")
        raise RuntimeError(f"无法打开 RTL-SDR 设备：{e}（检查驱动/USB 连接）") from e

    # configure once, before starting the reader thread
    sdr.sample_rate = getattr(cfg, "sample_rate", 2.4e6)
    sdr.center_freq = getattr(cfg, "center_freq", 1090e6)
    if getattr(cfg, "ppm", None):
        sdr.set_freq_correction(cfg.ppm)
    gain = getattr(cfg, "gain", None)
    if gain in (None, ""):
        gain = "40.2"
    _apply_gain(sdr, gain)
    try:
        sdr.set_agc_mode(False)
    except Exception:
        pass
    if radio is not None:
        try:
            tuner = sdr.get_tuner_type()
        except Exception:
            tuner = None
        radio.update(
            connected=True, tuner_type=tuner, current_gain=sdr.gain,
            sample_rate=sdr.sample_rate, freq=sdr.center_freq, error=None,
        )

    # Producer thread drains the USB at full rate into a bounded queue; the
    # demodulator (consumer) reads from it.  If the consumer falls behind, the
    # oldest chunk is dropped instead of letting the backlog grow unbounded.
    q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=4)
    stop = threading.Event()
    count = 0

    def producer() -> None:
        nonlocal count
        while not stop.is_set():
            if radio is not None:
                g = radio.take_gain_request()
                if g is not None:
                    applied = _apply_gain(sdr, g)
                    if applied is not None:
                        radio.update(current_gain=applied)
            try:
                samples = sdr.read_samples(_READ_SAMPLES)
            except Exception as e:
                # surface the failure, then wake the consumer with a sentinel
                if radio is not None:
                    radio.update(reading=False, error=f"读取失败：{e}")
                try:
                    q.put_nowait(None)
                except queue.Full:
                    pass
                break
            iq = np.asarray(samples)
            if not np.iscomplexobj(iq):
                iq = iq.astype("complex64")
            count += iq.size
            if radio is not None:
                radio.update(samples=count, peak=float(np.abs(iq[::4]).max()), reading=True)
            try:
                q.put_nowait(iq)
            except queue.Full:
                try:
                    q.get_nowait()  # drop the oldest stale chunk
                except queue.Empty:
                    pass
                q.put_nowait(iq)

    threading.Thread(target=producer, daemon=True, name="rtlsdr-reader").start()
    demod = Demodulator()
    try:
        while True:
            iq = q.get()
            if iq is None:  # producer died (device unplugged / read error)
                break
            if radio is not None:
                radio.update(noise_floor=demod.noise_floor)
            for frame in demod.feed(iq):
                yield frame
            if radio is not None:
                radio.update(noise_floor=demod.noise_floor)
    finally:
        stop.set()
        if radio is not None:
            radio.update(reading=False, connected=False)
        try:
            sdr.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# dump1090 / readsb network source
# ---------------------------------------------------------------------------


def _parse_avr(line: str) -> bytes | None:
    hexes = "".join(c for c in line if c in "0123456789abcdefABCDEF")
    if len(hexes) in (14, 28):
        try:
            return bytes.fromhex(hexes)
        except ValueError:
            return None
    return None


def _parse_sbs(line: str) -> bytes | None:
    # BaseStation CSV: MSG,type,...,hexid,...,alt,...,lat,lon,...
    parts = line.split(",")
    if len(parts) < 22 or parts[0] != "MSG":
        return None
    hexid = parts[4].strip()
    if len(hexid) != 12:
        return None
    # Reconstruct a DF17 frame with the position/ident we can; simplest is to
    # build an ident-style frame from the hexid + callsign so the tracker has
    # the ICAO and callsign; position is handled via lat/lon fields directly.
    try:
        icao = int(hexid, 16)
    except ValueError:
        return None
    callsign = parts[10].strip() or "        "
    return msgen.build_ident(icao, callsign)


class _BeastParser:
    def __init__(self):
        self.buf = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        self.buf += data
        out: list[bytes] = []
        while True:
            idx = self.buf.find(0x1A)
            if idx < 0:
                break
            if idx + 1 >= len(self.buf):
                break
            t = self.buf[idx + 1]
            if t == 0x1A:  # escaped literal
                del self.buf[: idx + 1]
                continue
            if t == 0x31:  # Mode-S short (7 bytes)
                mlat_len, msg_len = 6, 7
            elif t == 0x32:  # Mode-S long (14 bytes)
                mlat_len, msg_len = 6, 14
            else:
                del self.buf[: idx + 1]
                continue
            need = idx + 2 + mlat_len + 1 + msg_len  # header + ts + rssi + msg
            if len(self.buf) < need:
                break
            msg = bytes(self.buf[idx + 2 + mlat_len + 1 : need])
            out.append(msg)
            del self.buf[:need]
        if len(self.buf) > 8192:
            del self.buf[: len(self.buf) - 4096]
        return out


def network_source(cfg) -> Iterator[bytes]:
    import socket

    host = getattr(cfg, "host", "127.0.0.1")
    port = getattr(cfg, "port", 30002)
    sock = socket.create_connection((host, port), timeout=5.0)
    sock.settimeout(2.0)
    buf = bytearray()
    beast = _BeastParser()
    beast_mode: bool | None = None
    try:
        while True:
            try:
                data = sock.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            if not data:
                return
            if beast_mode is None:
                beast_mode = data[0] == 0x1A
            if beast_mode:
                for frame in beast.feed(data):
                    yield frame
            else:
                buf += data
                while b"\n" in buf:
                    line, _, buf = buf.partition(b"\n")
                    text = line.decode("ascii", "ignore").strip()
                    if not text:
                        continue
                    if text.startswith("MSG"):
                        frame = _parse_sbs(text)
                    else:
                        frame = _parse_avr(text)
                    if frame is not None:
                        yield frame
                if len(buf) > 8192:
                    del buf[: len(buf) - 4096]
    finally:
        try:
            sock.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def rtl_tcp_source(cfg, radio=None) -> Iterator[bytes]:
    """Read raw IQ from a local/remote rtl_tcp server and demodulate it.

    This is the non-root Android path: the "RTL-SDR Driver" app (package
    ``marto.rtl_tcp_andro``) opens the dongle through the Android USB stack
    (which does the high-bandwidth bulk transfers correctly) and re-serves the
    IQ stream over TCP; this process only demangles I/Q from a socket, so it
    never needs direct USB access.
    """
    import socket
    import struct

    import numpy as np

    host = getattr(cfg, "tcp_host", "127.0.0.1")
    port = int(getattr(cfg, "tcp_port", 1234))
    rate = int(getattr(cfg, "sample_rate", 2400000))
    freq = int(getattr(cfg, "center_freq", 1090000000))
    ppm = int(getattr(cfg, "ppm", 0) or 0)
    gain = getattr(cfg, "gain", None)
    if gain in (None, ""):
        gain = "40.2"

    deadline = time.time() + 10.0
    while True:
        try:
            sock = socket.create_connection((host, port), timeout=3.0)
            break
        except OSError:
            if time.time() > deadline:
                raise RuntimeError(f"rtl_tcp：连不上 {host}:{port}（确认 RTL-SDR Driver 的 TCP 已启动）")
            time.sleep(0.5)
    sock.settimeout(5.0)

    banner = b""
    while len(banner) < 4:
        part = sock.recv(4 - len(banner))
        if not part:
            raise RuntimeError("rtl_tcp：连接建立但收不到横幅（不是 rtl_tcp 服务）")
        banner += part
    if banner != b"RTL0":
        raise RuntimeError(f"rtl_tcp：横幅不对 {banner!r}（这不是 rtl_tcp 服务）")

    def _cmd(cmd: int, payload: bytes) -> None:
        sock.sendall(bytes([cmd]) + payload)

    def _apply_gain_cmd(value) -> None:
        if str(value).lower() == "auto":
            _cmd(0x03, struct.pack(">i", 0))          # auto gain mode
        else:
            _cmd(0x03, struct.pack(">i", 1))          # manual gain mode
            _cmd(0x04, struct.pack(">H", int(round(float(value) * 10))))  # gain, tenths of dB

    _cmd(0x02, struct.pack(">I", rate))               # sample rate
    _cmd(0x01, struct.pack(">I", freq))               # center frequency
    _cmd(0x08, struct.pack(">i", 0))                  # RTL2832 AGC off
    _apply_gain_cmd(gain)
    if ppm:
        _cmd(0x05, struct.pack(">h", ppm))            # frequency correction

    if radio is not None:
        radio.update(connected=True, reading=True, current_gain=gain,
                     sample_rate=rate, freq=freq, tuner_type=None, error=None)

    demod = Demodulator()
    chunk = _READ_SAMPLES * 2  # bytes per read (interleaved uint8 I/Q)
    count = 0
    try:
        while True:
            if radio is not None:
                g = radio.take_gain_request()
                if g is not None:
                    _apply_gain_cmd(g)
                    if radio is not None:
                        radio.update(current_gain=g)
            buf = bytearray()
            while len(buf) < chunk:
                part = sock.recv(chunk - len(buf))
                if not part:
                    raise RuntimeError("rtl_tcp：连接断开")
                buf.extend(part)
            raw = np.frombuffer(bytes(buf), dtype=np.uint8).astype(np.float32).reshape(-1, 2)
            iq = ((raw[:, 0] - 127.5) + 1j * (raw[:, 1] - 127.5)).astype(np.complex64)
            count += iq.size
            if radio is not None:
                radio.update(samples=count, peak=float(np.abs(iq[::4]).max()))
            for frame in demod.feed(iq):
                yield frame
            if radio is not None:
                radio.update(noise_floor=demod.noise_floor)
    finally:
        if radio is not None:
            radio.update(reading=False, connected=False)
        try:
            sock.close()
        except OSError:
            pass


def create_source(cfg, radio=None) -> Iterator[bytes]:
    src = getattr(cfg, "source", "rtlsdr")
    if src == "sim":
        return sim_source(cfg)
    if src == "transit_demo":
        return transit_demo_source(cfg)
    if src == "rtl_adsb":
        return rtl_adsb_source(cfg)
    if src == "network":
        return network_source(cfg)
    if src == "rtl_tcp":
        return rtl_tcp_source(cfg, radio)
    return rtlsdr_source(cfg, radio)
