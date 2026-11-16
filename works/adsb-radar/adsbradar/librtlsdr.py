"""Minimal pyrtlsdr-compatible ctypes binding for librtlsdr.

pyrtlsdr 0.5.x loads *every* librtlsdr symbol at import time, which breaks
against librtlsdr 2.0.x (which dropped a few legacy symbols such as
``rtlsdr_set_dithering``).  This tiny binding loads only the functions the
receiver actually uses and exposes a pyrtlsdr-like API, so it works with any
librtlsdr version — including the osmocom 2.0.x build used on Android.
"""

from __future__ import annotations

import ctypes
import ctypes.util

import numpy as np

_c_ubyte = ctypes.c_ubyte
_c_int = ctypes.c_int
_c_uint = ctypes.c_uint
_c_void_p = ctypes.c_void_p

_LIB = None


def _lib() -> ctypes.CDLL:
    global _LIB
    if _LIB is None:
        name = ctypes.util.find_library("rtlsdr") or "librtlsdr.so"
        lib = ctypes.CDLL(name)
        lib.rtlsdr_open.argtypes = [ctypes.POINTER(_c_void_p), _c_uint]
        lib.rtlsdr_open.restype = _c_int
        lib.rtlsdr_set_center_freq.argtypes = [_c_void_p, _c_uint]
        lib.rtlsdr_set_center_freq.restype = _c_int
        lib.rtlsdr_set_sample_rate.argtypes = [_c_void_p, _c_uint]
        lib.rtlsdr_set_sample_rate.restype = _c_int
        lib.rtlsdr_set_tuner_gain.argtypes = [_c_void_p, _c_int]
        lib.rtlsdr_set_tuner_gain.restype = _c_int
        lib.rtlsdr_set_tuner_gain_mode.argtypes = [_c_void_p, _c_int]
        lib.rtlsdr_set_tuner_gain_mode.restype = _c_int
        lib.rtlsdr_set_agc_mode.argtypes = [_c_void_p, _c_int]
        lib.rtlsdr_set_agc_mode.restype = _c_int
        lib.rtlsdr_set_freq_correction.argtypes = [_c_void_p, _c_int]
        lib.rtlsdr_set_freq_correction.restype = _c_int
        lib.rtlsdr_get_tuner_type.argtypes = [_c_void_p]
        lib.rtlsdr_get_tuner_type.restype = _c_int
        lib.rtlsdr_reset_buffer.argtypes = [_c_void_p]
        lib.rtlsdr_reset_buffer.restype = _c_int
        lib.rtlsdr_read_sync.argtypes = [_c_void_p, ctypes.POINTER(_c_ubyte), _c_int, ctypes.POINTER(_c_int)]
        lib.rtlsdr_read_sync.restype = _c_int
        lib.rtlsdr_close.argtypes = [_c_void_p]
        lib.rtlsdr_close.restype = _c_int
        _LIB = lib
    return _LIB


class RTLSDR:
    """A pyrtlsdr-compatible subset: property-style tuner setup + read_samples()."""

    def __init__(self, index: int = 0) -> None:
        lib = _lib()
        self._lib = lib
        self._dev = _c_void_p()
        self._sample_rate = 0
        self._center_freq = 0
        self._gain = "auto"
        ret = lib.rtlsdr_open(ctypes.byref(self._dev), _c_uint(index))
        if ret != 0:
            raise RuntimeError(f"rtlsdr_open failed (code {ret})")

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @sample_rate.setter
    def sample_rate(self, hz: int) -> None:
        self._sample_rate = int(hz)
        self._lib.rtlsdr_set_sample_rate(self._dev, _c_uint(int(hz)))

    @property
    def center_freq(self) -> int:
        return self._center_freq

    @center_freq.setter
    def center_freq(self, hz: int) -> None:
        self._center_freq = int(hz)
        self._lib.rtlsdr_set_center_freq(self._dev, _c_uint(int(hz)))

    @property
    def gain(self):
        return self._gain

    @gain.setter
    def gain(self, value) -> None:
        if str(value).lower() == "auto":
            self._lib.rtlsdr_set_tuner_gain_mode(self._dev, _c_int(0))  # AGC
            self._gain = "auto"
        else:
            db = float(value)
            self._lib.rtlsdr_set_tuner_gain_mode(self._dev, _c_int(1))  # manual
            self._lib.rtlsdr_set_tuner_gain(self._dev, _c_int(int(round(db * 10))))
            self._gain = db

    def set_freq_correction(self, ppm: int) -> None:
        self._lib.rtlsdr_set_freq_correction(self._dev, _c_int(int(ppm)))

    def set_agc_mode(self, on: bool) -> None:
        self._lib.rtlsdr_set_agc_mode(self._dev, _c_int(1 if on else 0))

    def get_tuner_type(self) -> int:
        return int(self._lib.rtlsdr_get_tuner_type(self._dev))

    def read_samples(self, n: int) -> np.ndarray:
        buf = (_c_ubyte * (n * 2))()
        n_read = _c_int(0)
        ret = self._lib.rtlsdr_read_sync(self._dev, buf, _c_int(n * 2), ctypes.byref(n_read))
        if ret != 0:
            raise RuntimeError(f"rtlsdr_read_sync failed (code {ret})")
        cnt = n_read.value // 2 * 2
        raw = np.frombuffer(bytes(buf[:cnt]), dtype=np.uint8).astype(np.float32).reshape(-1, 2)
        return ((raw[:, 0] - 127.5) + 1j * (raw[:, 1] - 127.5)).astype(np.complex64)

    def close(self) -> None:
        if self._dev:
            self._lib.rtlsdr_close(self._dev)
            self._dev = _c_void_p()
