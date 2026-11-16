"""Local HTTP server: serves the radar web UI and a JSON state endpoint."""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__
from .crc import icao_and_check
from .decode import parse_frame
from .radio import Radio
from .sources import create_source
from .tracker import Tracker
from .transit import TransitCalculator

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")

_MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


class RateMeter:
    def __init__(self, window: float = 5.0) -> None:
        self.window = window
        self.times: deque[float] = deque()
        self._lock = threading.Lock()

    def tick(self) -> None:
        now = time.time()
        with self._lock:
            self.times.append(now)
            while self.times and now - self.times[0] > self.window:
                self.times.popleft()

    def rate(self) -> float:
        now = time.time()
        with self._lock:
            while self.times and now - self.times[0] > self.window:
                self.times.popleft()
            return round(len(self.times) / self.window, 2)


class State:
    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.tracker = Tracker(cfg.lat, cfg.lon, getattr(cfg, "max_range_km", 700.0))
        self.radio = Radio()
        self.source = create_source(cfg, self.radio)
        self.msg_meter = RateMeter()
        self.pos_meter = RateMeter()
        self.started = time.time()
        self.last_ui = time.time()
        self._snap = {"aircraft": [], "stats": {}}
        self._lock = threading.Lock()
        self.source_name = getattr(cfg, "source", "rtlsdr")
        self._source_error = None
        self._dead = threading.Event()
        self.transit = TransitCalculator(cfg.lat, cfg.lon, getattr(cfg, "alt_m", 0.0))

    def _process_loop(self) -> None:
        try:
            for frame in self.source:
                if self._dead.is_set():
                    break
                self.msg_meter.tick()
                if len(frame) != 14:
                    continue
                icao, ok = icao_and_check(frame)
                if not ok:
                    self.tracker.n_crc_bad += 1
                    continue
                msg = parse_frame(frame)
                if msg is None:
                    continue
                if icao and not msg.get("icao"):
                    msg["icao"] = icao
                self.tracker.update(msg, time.time())
                if msg.get("kind") in ("airborne_pos", "surface_pos"):
                    self.pos_meter.tick()
        except Exception as e:  # keep the radar alive; surface the failure in the UI
            self._source_error = f"{type(e).__name__}: {e}"
            self.radio.update(error=f"{type(e).__name__}: {e}", connected=False, reading=False)
            import traceback

            traceback.print_exc()

    def start(self) -> None:
        t = threading.Thread(target=self._process_loop, daemon=True, name="adsb-source")
        t.start()

    def stop(self) -> None:
        self._dead.set()

    def state_json(self) -> dict:
        now = time.time()
        self.tracker.expire(now)
        ac = self.tracker.snapshot(now)
        with_pos = sum(1 for a in ac if a["lat"] is not None)
        max_range = max((a["dist_km"] for a in ac if a["dist_km"] is not None), default=0.0)
        center = self.tracker.center()
        if center is not None:
            self.transit.set_location(center[0], center[1])
        transits, bodies = self.transit.predict(ac, now)
        return {
            "t": round(now, 3),
            "version": __version__,
            "source": self.source_name,
            "source_error": self._source_error,
            "radio": self.radio.snapshot(),
            "range_km": getattr(self.cfg, "range_km", 250.0),
            "station": {
                "lat": self.tracker.lat,
                "lon": self.tracker.lon,
                "set": self.tracker.lat is not None,
            },
            "origin": {"lat": center[0], "lon": center[1]} if center else None,
            "stats": {
                "aircraft": len(ac),
                "with_pos": with_pos,
                "msg_per_s": self.msg_meter.rate(),
                "pos_per_s": self.pos_meter.rate(),
                "crc_bad": self.tracker.n_crc_bad,
                "max_range_km": round(max_range, 1),
            },
            "transit": {
                "bodies": bodies,
                "upcoming": transits,
            },
            "aircraft": ac,
        }


def _handler_for(state: State):
    class Handler(BaseHTTPRequestHandler):
        server_version = "adsb-radar/" + __version__

        def log_message(self, fmt, *args):  # keep console quiet
            pass

        def _send_json(self, obj, code=200):
            body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_file(self, rel):
            if rel in ("", "/"):
                rel = "index.html"
            path = os.path.normpath(os.path.join(WEB_DIR, rel.lstrip("/")))
            if not path.startswith(WEB_DIR):
                self.send_error(403)
                return
            if not os.path.isfile(path):
                self.send_error(404)
                return
            ext = os.path.splitext(path)[1].lower()
            try:
                with open(path, "rb") as f:
                    body = f.read()
            except OSError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", _MIME.get(ext, "application/octet-stream"))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/api/state"):
                self._send_json(state.state_json())
            elif self.path.startswith("/api/meta"):
                s = state.state_json()
                self._send_json(
                    {
                        "version": __version__,
                        "source": state.source_name,
                        "range_km": s["range_km"],
                        "station": s["station"],
                    }
                )
            else:
                self._send_file(self.path.split("?", 1)[0])

        def do_POST(self):
            if not self.path.startswith("/api/config"):
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception:
                self._send_json({"error": "bad request"}, 400)
                return
            if "gain" in data:
                state.radio.request_gain(data["gain"])
            self._send_json({"ok": True, "radio": state.radio.snapshot()})

    return Handler


def run(cfg) -> None:
    state = State(cfg)
    state.start()
    host = getattr(cfg, "host_bind", "0.0.0.0")
    port = int(getattr(cfg, "port", 8080))
    httpd = ThreadingHTTPServer((host, port), _handler_for(state))
    httpd.daemon_threads = True
    url = f"http://127.0.0.1:{port}/"
    lan_url = f"http://{_lan_ip()}:{port}/" if _lan_ip() else None
    print("=" * 60)
    print("  ADS-B 雷达  RTL-SDR V4")
    print(f"  数据源     : {state.source_name}")
    if state.tracker.lat is not None:
        print(f"  接收站     : {state.tracker.lat:.4f}N, {state.tracker.lon:.4f}E")
    else:
        print("  接收站     : 未设置（将自动以首个目标为中心）")
    print(f"  雷达半径   : {getattr(cfg, 'range_km', 250.0):.0f} km")
    print(f"  本机打开   : {url}")
    if lan_url:
        print(f"  手机/局域网: {lan_url}")
    print("  按 Ctrl+C 退出")
    print("=" * 60)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        state.stop()
        httpd.shutdown()
        httpd.server_close()


def _lan_ip() -> str | None:
    import socket

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return None
