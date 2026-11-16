"""Thread-safe runtime state + control for the RTL-SDR receiver.

Shared between the source thread (which owns the libusb device and is the only
place allowed to touch it) and the HTTP server thread (which reads status and
queues gain changes).
"""

from __future__ import annotations

import threading


class Radio:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending_gain: str | None = None
        # status (written by the source thread)
        self.connected = False
        self.reading = False
        self.samples = 0
        self.noise_floor = 0.0
        self.peak = 0.0
        self.tuner_type: int | None = None
        self.current_gain = None
        self.sample_rate = 0.0
        self.freq = 0.0
        self.error: str | None = None

    # -- control (server -> source) -------------------------------------
    def request_gain(self, value) -> None:
        with self._lock:
            self._pending_gain = str(value)

    def take_gain_request(self) -> str | None:
        with self._lock:
            v = self._pending_gain
            self._pending_gain = None
            return v

    # -- status (source -> server) --------------------------------------
    def update(self, **kw) -> None:
        with self._lock:
            for k, v in kw.items():
                setattr(self, k, v)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "connected": self.connected,
                "reading": self.reading,
                "samples": self.samples,
                "noise_floor": round(self.noise_floor, 4),
                "peak": round(self.peak, 4),
                "tuner_type": self.tuner_type,
                "gain": self.current_gain,
                "sample_rate": self.sample_rate,
                "freq": self.freq,
                "error": self.error,
            }
