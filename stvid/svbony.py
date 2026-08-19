#!/usr/bin/env python3

import ctypes
import os


class SVBonyError(RuntimeError):
    pass


class SVBonyCamera:
    """
    Thin Python wrapper around libstvid_svbony.so.

    The C wrapper hides the proprietary SVBONY SDK ABI and exposes
    only the functions STVID needs.
    """

    def __init__(self, library, device_id, width, height,
                 exposure, gain, timeout=5000):

        self.device_id = device_id
        self.width = width
        self.height = height
        self.timeout = timeout

        self.lib = ctypes.CDLL(library)

        self.lib.stvid_svbony_open.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_long,
            ctypes.c_long,
        ]
        self.lib.stvid_svbony_open.restype = ctypes.c_int

        self.lib.stvid_svbony_get_frame.argtypes = [
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_long,
            ctypes.c_int,
        ]
        self.lib.stvid_svbony_get_frame.restype = ctypes.c_int

        self.lib.stvid_svbony_stop.argtypes = [
            ctypes.c_int,
        ]
        self.lib.stvid_svbony_stop.restype = ctypes.c_int

        self.lib.stvid_svbony_close.argtypes = [
            ctypes.c_int,
        ]
        self.lib.stvid_svbony_close.restype = ctypes.c_int

        self.lib.stvid_svbony_num_cameras.argtypes = []
        self.lib.stvid_svbony_num_cameras.restype = ctypes.c_int

        self.lib.stvid_svbony_dropped_frames.argtypes = [
            ctypes.c_int,
        ]
        self.lib.stvid_svbony_dropped_frames.restype = ctypes.c_int


        result = self.lib.stvid_svbony_open(
            device_id,
            width,
            height,
            exposure,
            gain,
        )

        if result != 0:
            raise SVBonyError(
                "Unable to open SVBONY camera "
                f"(error {result})"
            )

        self._opened = True

    def get_frame(self, buffer):
        """
        Fill a ctypes buffer with one RAW8 frame.
        """

        result = self.lib.stvid_svbony_get_frame(
            self.device_id,
            ctypes.cast(buffer, ctypes.c_void_p),
            self.width * self.height,
            self.timeout,
        )

        return result

    def dropped_frames(self):
        return self.lib.stvid_svbony_dropped_frames(
            self.device_id
        )

    def close(self):
        if not self._opened:
            return

        self.lib.stvid_svbony_stop(self.device_id)
        self.lib.stvid_svbony_close(self.device_id)

        self._opened = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

