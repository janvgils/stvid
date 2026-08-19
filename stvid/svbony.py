#!/usr/bin/env python3

import ctypes
import ctypes.util


class SVBonyError(RuntimeError):
    """Exception raised for SVBONY camera errors."""


class SVBonyCamera:
    """
    Python interface to the STVID SVBONY C wrapper.

    The device_id passed to this class is the SVBONY camera INDEX
    (0, 1, ...), not the SDK CameraID.

    The C wrapper takes care of translating:

        camera index -> SVB_CAMERA_INFO.CameraID
    """

    def __init__(
        self,
        library,
        device_id,
        width,
        height,
        exposure,
        gain,
        timeout=5000,
    ):
        self.library = library

        # This is the connected-camera index.
        # The C wrapper converts this to the real SVB CameraID.
        self.device_id = int(device_id)

        self.width = int(width)
        self.height = int(height)
        self.exposure = int(exposure)
        self.gain = int(gain)
        self.timeout = int(timeout)

        self._opened = False

        # ---------------------------------------------------------
        # Load libusb before libSVBCameraSDK.
        #
        # The SVBONY SDK depends on libusb and expects its symbols
        # to be globally available.
        # ---------------------------------------------------------

        libusb = ctypes.util.find_library("usb-1.0")

        if libusb is None:
            raise SVBonyError(
                "libusb-1.0 could not be found. "
                "Please install libusb-1.0."
            )

        try:
            self._libusb = ctypes.CDLL(
                libusb,
                mode=ctypes.RTLD_GLOBAL,
            )
        except OSError as exc:
            raise SVBonyError(
                f"Unable to load libusb-1.0: {exc}"
            ) from exc

        # ---------------------------------------------------------
        # Load the STVID SVBONY wrapper.
        # ---------------------------------------------------------

        try:
            self.lib = ctypes.CDLL(
                library,
                mode=ctypes.RTLD_GLOBAL,
            )
        except OSError as exc:
            raise SVBonyError(
                f"Unable to load SVBONY library "
                f"{library}: {exc}"
            ) from exc

        # ---------------------------------------------------------
        # C function definitions
        # ---------------------------------------------------------

        # int stvid_svbony_num_cameras(void);
        self.lib.stvid_svbony_num_cameras.argtypes = []

        self.lib.stvid_svbony_num_cameras.restype = ctypes.c_int

        # int stvid_svbony_open(
        #     int camera_index,
        #     int width,
        #     int height,
        #     long exposure,
        #     long gain
        # );
        self.lib.stvid_svbony_open.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_long,
            ctypes.c_long,
        ]

        self.lib.stvid_svbony_open.restype = ctypes.c_int

        # int stvid_svbony_get_frame(
        #     int camera_index,
        #     unsigned char *buffer,
        #     long buffer_size,
        #     int timeout_ms
        # );
        self.lib.stvid_svbony_get_frame.argtypes = [
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_long,
            ctypes.c_int,
        ]

        self.lib.stvid_svbony_get_frame.restype = ctypes.c_int

        # int stvid_svbony_stop(int camera_index);
        self.lib.stvid_svbony_stop.argtypes = [
            ctypes.c_int,
        ]

        self.lib.stvid_svbony_stop.restype = ctypes.c_int

        # int stvid_svbony_close(int camera_index);
        self.lib.stvid_svbony_close.argtypes = [
            ctypes.c_int,
        ]

        self.lib.stvid_svbony_close.restype = ctypes.c_int

        # int stvid_svbony_dropped_frames(int camera_index);
        self.lib.stvid_svbony_dropped_frames.argtypes = [
            ctypes.c_int,
        ]

        self.lib.stvid_svbony_dropped_frames.restype = ctypes.c_int

        # ---------------------------------------------------------
        # Check that the requested camera index exists.
        # ---------------------------------------------------------

        camera_count = self.lib.stvid_svbony_num_cameras()

        if camera_count < 0:
            raise SVBonyError(
                "Unable to determine number of SVBONY cameras."
            )

        if self.device_id < 0 or self.device_id >= camera_count:
            raise SVBonyError(
                f"SVBONY camera index {self.device_id} is invalid. "
                f"{camera_count} camera(s) detected."
            )

        # ---------------------------------------------------------
        # Open and configure camera.
        #
        # IMPORTANT:
        # device_id is the camera INDEX.
        # The C wrapper converts it to CameraID.
        # ---------------------------------------------------------

        result = self.lib.stvid_svbony_open(
            self.device_id,
            self.width,
            self.height,
            self.exposure,
            self.gain,
        )

        if result != 0:
            raise SVBonyError(
                f"Unable to open SVBONY camera "
                f"index {self.device_id}, "
                f"SDK error {result}"
            )

        self._opened = True

    # -------------------------------------------------------------
    # Frame acquisition
    # -------------------------------------------------------------

    def get_frame(self, buffer):
        """
        Get one RAW8 frame.

        `buffer` must be a ctypes-compatible writable buffer
        containing at least width * height bytes.
        """

        if not self._opened:
            raise SVBonyError(
                "Camera is not open."
            )

        buffer_size = self.width * self.height

        result = self.lib.stvid_svbony_get_frame(
            self.device_id,
            buffer,
            buffer_size,
            self.timeout,
        )

        return result

    # -------------------------------------------------------------
    # Dropped frames
    # -------------------------------------------------------------

    def dropped_frames(self):
        """
        Return the number of dropped frames reported by the
        SVBONY SDK.

        Returns -1 if the value cannot be obtained.
        """

        if not self._opened:
            return -1

        return self.lib.stvid_svbony_dropped_frames(
            self.device_id
        )

    # -------------------------------------------------------------
    # Stop capture
    # -------------------------------------------------------------

    def stop(self):
        """
        Stop video capture.

        This does not close the camera.
        """

        if not self._opened:
            return 0

        return self.lib.stvid_svbony_stop(
            self.device_id
        )

    # -------------------------------------------------------------
    # Close
    # -------------------------------------------------------------

    def close(self):
        """
        Stop capture and close the camera.
        """

        if not self._opened:
            return

        # Stop capture first.
        self.lib.stvid_svbony_stop(
            self.device_id
        )

        # Then close the camera.
        self.lib.stvid_svbony_close(
            self.device_id
        )

        self._opened = False

    # -------------------------------------------------------------
    # Context manager support
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
    # Properties
    # -------------------------------------------------------------

    @property
    def opened(self):
        """Return True if the camera is currently open."""
        return self._opened
