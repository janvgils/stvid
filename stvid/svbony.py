#!/usr/bin/env python3

import ctypes
import ctypes.util


class SVBonyError(RuntimeError):
    pass


class SVBonyCamera:

    def __init__(
        self,
        library,
        device_id=0,
        width=1920,
        height=1080,
        exposure=10000,
        gain=10,
        timeout=5000,
    ):
        self.device_id = int(device_id)

        self.requested_width = int(width)
        self.requested_height = int(height)

        self.exposure = int(exposure)
        self.gain = int(gain)
        self.timeout = int(timeout)

        self.width = 0
        self.height = 0
        self.bytes_per_pixel = 0
        self.image_type = -1
        self.camera_id = -1

        self._opened = False

        # ---------------------------------------------------------
        # libusb must be loaded globally before the SVBONY SDK.
        # ---------------------------------------------------------

        libusb_name = ctypes.util.find_library(
            "usb-1.0"
        )

        if not libusb_name:
            raise SVBonyError(
                "libusb-1.0 not found"
            )

        try:
            self._libusb = ctypes.CDLL(
                libusb_name,
                mode=ctypes.RTLD_GLOBAL,
            )
        except OSError as exc:
            raise SVBonyError(
                f"Unable to load libusb-1.0: {exc}"
            ) from exc

        # ---------------------------------------------------------
        # Load wrapper.
        # ---------------------------------------------------------

        try:
            self.lib = ctypes.CDLL(
                library,
                mode=ctypes.RTLD_GLOBAL,
            )
        except OSError as exc:
            raise SVBonyError(
                f"Unable to load SVBONY wrapper "
                f"{library}: {exc}"
            ) from exc

        self._setup_api()

        # ---------------------------------------------------------
        # Detect cameras.
        # ---------------------------------------------------------

        count = (
            self.lib.stvid_svbony_num_cameras()
        )

        if count <= 0:
            raise SVBonyError(
                "No SVBONY cameras detected"
            )

        if self.device_id >= count:
            raise SVBonyError(
                f"Camera index {self.device_id} "
                f"is invalid; {count} camera(s) detected"
            )

        print(
            f"SVBONY: opening camera index "
            f"{self.device_id}"
        )

        # ---------------------------------------------------------
        # Open/configure.
        # ---------------------------------------------------------

        result = self.lib.stvid_svbony_open(
            self.device_id,
            self.requested_width,
            self.requested_height,
            self.exposure,
            self.gain,
        )

        if result != 0:
            raise SVBonyError(
                f"Unable to open SVBONY camera "
                f"{self.device_id}, SDK error {result}"
            )

        self._opened = True

        # ---------------------------------------------------------
        # Read actual configuration selected by C layer.
        # ---------------------------------------------------------

        self.width = (
            self.lib.stvid_svbony_width(
                self.device_id
            )
        )

        self.height = (
            self.lib.stvid_svbony_height(
                self.device_id
            )
        )

        self.bytes_per_pixel = (
            self.lib.stvid_svbony_bytes_per_pixel(
                self.device_id
            )
        )

        self.image_type = (
            self.lib.stvid_svbony_image_type(
                self.device_id
            )
        )

        self.camera_id = (
            self.lib.stvid_svbony_camera_id(
                self.device_id
            )
        )

        print(
            "SVBONY: CameraID:",
            self.camera_id
        )

        print(
            "SVBONY: resolution:",
            f"{self.width}x{self.height}"
        )

        print(
            "SVBONY: bytes/pixel:",
            self.bytes_per_pixel
        )

        print(
            "SVBONY: image type:",
            self.image_type
        )

        print(
            "SVBONY: camera opened"
        )

    # -------------------------------------------------------------
    # ctypes API
    # -------------------------------------------------------------

    def _setup_api(self):

        self.lib.stvid_svbony_num_cameras.argtypes = []
        self.lib.stvid_svbony_num_cameras.restype = (
            ctypes.c_int
        )

        self.lib.stvid_svbony_open.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_long,
            ctypes.c_long,
        ]

        self.lib.stvid_svbony_open.restype = (
            ctypes.c_int
        )

        self.lib.stvid_svbony_width.argtypes = [
            ctypes.c_int
        ]

        self.lib.stvid_svbony_width.restype = (
            ctypes.c_int
        )

        self.lib.stvid_svbony_height.argtypes = [
            ctypes.c_int
        ]

        self.lib.stvid_svbony_height.restype = (
            ctypes.c_int
        )

        self.lib.stvid_svbony_bytes_per_pixel.argtypes = [
            ctypes.c_int
        ]

        self.lib.stvid_svbony_bytes_per_pixel.restype = (
            ctypes.c_int
        )

        self.lib.stvid_svbony_image_type.argtypes = [
            ctypes.c_int
        ]

        self.lib.stvid_svbony_image_type.restype = (
            ctypes.c_int
        )

        self.lib.stvid_svbony_camera_id.argtypes = [
            ctypes.c_int
        ]

        self.lib.stvid_svbony_camera_id.restype = (
            ctypes.c_int
        )

        self.lib.stvid_svbony_get_frame.argtypes = [
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_long,
            ctypes.c_int,
        ]

        self.lib.stvid_svbony_get_frame.restype = (
            ctypes.c_int
        )

        self.lib.stvid_svbony_stop.argtypes = [
            ctypes.c_int
        ]

        self.lib.stvid_svbony_stop.restype = (
            ctypes.c_int
        )

        self.lib.stvid_svbony_close.argtypes = [
            ctypes.c_int
        ]

        self.lib.stvid_svbony_close.restype = (
            ctypes.c_int
        )

        self.lib.stvid_svbony_dropped_frames.argtypes = [
            ctypes.c_int
        ]

        self.lib.stvid_svbony_dropped_frames.restype = (
            ctypes.c_int
        )

    # -------------------------------------------------------------
    # Frame size
    # -------------------------------------------------------------

    @property
    def frame_size(self):
        return (
            self.width
            * self.height
            * self.bytes_per_pixel
        )

    # -------------------------------------------------------------
    # Frame acquisition
    # -------------------------------------------------------------

    def get_frame(self):

        if not self._opened:
            raise SVBonyError(
                "Camera is not open"
            )

        buffer = (
            ctypes.c_ubyte * self.frame_size
        )()

        result = self.lib.stvid_svbony_get_frame(
            self.device_id,
            buffer,
            self.frame_size,
            self.timeout,
        )

        if result != 0:
            raise SVBonyError(
                f"SVBGetVideoData failed: "
                f"SDK error {result}"
            )

        return buffer

    # -------------------------------------------------------------
    # Get frame into an existing ctypes buffer.
    # -------------------------------------------------------------

    def get_frame_into(self, buffer):

        if not self._opened:
            raise SVBonyError(
                "Camera is not open"
            )

        result = self.lib.stvid_svbony_get_frame(
            self.device_id,
            buffer,
            self.frame_size,
            self.timeout,
        )

        if result != 0:
            raise SVBonyError(
                f"SVBGetVideoData failed: "
                f"SDK error {result}"
            )

        return result

    # -------------------------------------------------------------
    # Dropped frames
    # -------------------------------------------------------------

    def dropped_frames(self):

        if not self._opened:
            return -1

        return (
            self.lib.stvid_svbony_dropped_frames(
                self.device_id
            )
        )

    # -------------------------------------------------------------
    # Stop
    # -------------------------------------------------------------

    def stop(self):

        if not self._opened:
            return 0

        return self.lib.stvid_svbony_stop(
            self.device_id
        )

    # -------------------------------------------------------------
    # Close
    # -------------------------------------------------------------

    def close(self):

        if not self._opened:
            return

        self.lib.stvid_svbony_close(
            self.device_id
        )

        self._opened = False

    # -------------------------------------------------------------
    # Context manager
    # -------------------------------------------------------------

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        self.close()

    # -------------------------------------------------------------
    # State
    # -------------------------------------------------------------

    @property
    def opened(self):
        return self._opened
