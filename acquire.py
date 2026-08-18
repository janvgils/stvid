#!/usr/bin/env python3
import sys
import os
import numpy as np
import cv2
import time
import ctypes
import multiprocessing
from astropy.coordinates import EarthLocation
from astropy.time import Time
from astropy.io import fits
import astropy.units as u
from stvid.utils import observe_logic
import logging
import configparser
import argparse

def setup_logging(path):
    logFormatter = logging.Formatter(
        "%(asctime)s [%(processName)-12.12s] [%(levelname)-5.5s] %(message)s"
    )
    logger = logging.getLogger()
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)

    fileHandler = logging.FileHandler(os.path.join(path, "acquire.log"))
    fileHandler.setFormatter(logFormatter)
    logger.addHandler(fileHandler)

    consoleHandler = logging.StreamHandler(sys.stdout)
    consoleHandler.setFormatter(logFormatter)
    logger.addHandler(consoleHandler)

    return logger

# Capture images from pi
def capture_pi(image_queue, z1base, t1base, z2base, t2base, nx, ny, nz, tend, device_id, live, conf_file):
    global logger
    logger = setup_logging(os.getcwd())

    cfg = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    cfg.read(conf_file)
    
    from picamerax.array import PiRGBArray
    from picamerax import PiCamera

    z1 = np.ctypeslib.as_array(z1base.get_obj()).reshape(ny, nx, nz)
    t1 = np.ctypeslib.as_array(t1base.get_obj())
    z2 = np.ctypeslib.as_array(z2base.get_obj()).reshape(ny, nx, nz)
    t2 = np.ctypeslib.as_array(t2base.get_obj())
    
    # Intialization
    first = True
    slow_CPU = False

    # Initialize cv2 device
    camera = PiCamera(sensor_mode=2)
    camera.resolution = (nx, ny)    
    # Turn off any thing automatic.
    camera.exposure_mode = "off"        
    camera.awb_mode = "off"
    # ISO needs to be 0 otherwise analog and digital gain won't work.
    camera.iso = 0
    # set the camea settings
    camera.framerate = cfg.getfloat(camera_type, "framerate")
    camera.awb_gains = (cfg.getfloat(camera_type, "awb_gain_red"), cfg.getfloat(camera_type, "awb_gain_blue"))    
    camera.analog_gain = cfg.getfloat(camera_type, "analog_gain")
    camera.digital_gain = cfg.getfloat(camera_type, "digital_gain")
    camera.shutter_speed = cfg.getint(camera_type, "exposure")

    rawCapture = PiRGBArray(camera, size=(nx, ny))
    # allow the camera to warmup
    time.sleep(0.1)

    try:
        # Loop until reaching end time
        while float(time.time()) < tend:
            # Wait for available capture buffer to become available
            if (image_queue.qsize() > 1):
                logger.warning("Acquiring data faster than your CPU can process")
                slow_CPU = True
            while (image_queue.qsize() > 1):
                time.sleep(0.1)
            if slow_CPU:
                lost_video = time.time() - t
                logger.info("Waited %.3fs for available capture buffer" % lost_video)
                slow_CPU = False

            # Get frames
            i = 0
            for frameA in camera.capture_continuous(rawCapture, format="bgr", use_video_port=True):
                            
                # Store start time
                t0 = float(time.time())                
                # grab the raw NumPy array representing the image, then initialize the timestamp                
                frame = frameA.array
                                    
                # Compute mid time
                t = (float(time.time()) + t0) / 2
                
                # Skip lost frames
                if frame is not None:
                    # Convert image to grayscale
                    z = np.asarray(cv2.cvtColor(
                        frame, cv2.COLOR_BGR2GRAY)).astype(np.uint8)
                    # optionally rotate the frame by 2 * 90 degrees.    
                    # z = np.rot90(z, 2)
                
                    # Display Frame
                    if live is True:                            
                        cv2.imshow("Capture", z)    
                        cv2.waitKey(1)
                    
                    # Store results
                    if first:
                        z1[:, :, i] = z
                        t1[i] = t
                    else:
                        z2[:, :, i] = z
                        t2[i] = t
                        
                # clear the stream in preparation for the next frame
                rawCapture.truncate(0)
                # count up to nz frames, then break out of the for loop.
                i += 1
                if i >= nz:
                    break
                
            if first: 
                buf = 1
            else:
                buf = 2
            image_queue.put(buf)
            logger.debug("Captured buffer %d" % buf)

            # Swap flag
            first = not first
        reason = "Session complete"
    except KeyboardInterrupt:
        print()
        reason = "Keyboard interrupt"
    except ValueError as e:
        logger.error("%s" % e)
        reason = "Wrong image dimensions? Fix nx, ny in config."
    finally:
        # End capture
        logger.info("Capture: %s - Exiting" % reason)
        camera.close()



# Capture images from cv2
def capture_cv2(image_queue, z1base, t1base, z2base, t2base, nx, ny, nz, tend, device_id, live, conf_file):
    global logger
    logger = setup_logging(os.getcwd())

    cfg = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    cfg.read(conf_file)

    z1 = np.ctypeslib.as_array(z1base.get_obj()).reshape(ny, nx, nz)
    t1 = np.ctypeslib.as_array(t1base.get_obj())
    z2 = np.ctypeslib.as_array(z2base.get_obj()).reshape(ny, nx, nz)
    t2 = np.ctypeslib.as_array(t2base.get_obj())
    
    # Intialization
    camera_type  = "CV2"
    first = True
    slow_CPU = False

    # Initialize cv2 device
    if cfg.has_option(camera_type, "device_string"):
        device = cv2.VideoCapture(cfg.get(camera_type, "device_string"))
    else:
        device = cv2.VideoCapture(device_id)

    # Test for software binning
    try:
        software_bin = cfg.getint(camera_type, "software_bin")
    except configparser.Error:
        software_bin = 1
    
    # Set properties
    device.set(3, nx * software_bin)
    device.set(4, ny * software_bin)
   
    try:
        # Loop until reaching end time
        while float(time.time()) < tend:
            # Wait for available capture buffer to become available
            if (image_queue.qsize() > 1):
                logger.warning("Acquiring data faster than your CPU can process")
                slow_CPU = True
            while (image_queue.qsize() > 1):
                time.sleep(0.1)
            if slow_CPU:
                lost_video = time.time() - t
                logger.info("Waited %.3fs for available capture buffer" % lost_video)
                slow_CPU = False

            # Get frames
            for i in range(nz):
                # Store start time
                t0 = float(time.time())

                # Get frame
                res, frame = device.read()

                # Compute mid time
                t = (float(time.time()) + t0) / 2

                # Skip lost frames
                if res is True:
                    # Convert image to grayscale
                    z = np.asarray(cv2.cvtColor(
                        frame, cv2.COLOR_BGR2GRAY)).astype(np.uint8)

                    # Apply software binning
                    if software_bin > 1:
                        my, mx = z.shape
                        z = cv2.resize(z, (mx // software_bin, my // software_bin))
                    
                    # Display Frame
                    if live is True:
                        cv2.imshow("Capture", z)
                        cv2.waitKey(1)

                    # Store results
                    if first:
                        z1[:, :, i] = z
                        t1[i] = t
                    else:
                        z2[:, :, i] = z
                        t2[i] = t

            if first: 
                buf = 1
            else:
                buf = 2
            image_queue.put(buf)
            logger.debug("Captured z%d" % buf)

            # Swap flag
            first = not first
        reason = "Session complete"
    except KeyboardInterrupt:
        print()
        reason = "Keyboard interrupt"
    except ValueError as e:
        logger.error("%s" % e)
        reason = "Wrong image dimensions? Fix nx, ny in config."
    finally:
        # End capture
        logger.info("Capture: %s - Exiting" % reason)
        device.release()


# Capture images from ASI
def capture_asi(image_queue, z1base, t1base, z2base, t2base, nx, ny, nz, tend, device_id, live, conf_file):
    global logger
    logger = setup_logging(os.getcwd())

    cfg = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    cfg.read(conf_file)
    
    import zwoasi as asi

    z1 = np.ctypeslib.as_array(z1base.get_obj()).reshape(ny, nx, nz)
    t1 = np.ctypeslib.as_array(t1base.get_obj())
    z2 = np.ctypeslib.as_array(z2base.get_obj()).reshape(ny, nx, nz)
    t2 = np.ctypeslib.as_array(t2base.get_obj())
    
    first    = True  # Array flag
    slow_CPU = False # Performance issue flag

    
    camera_type  = "ASI"
    gain         = cfg.getint(camera_type, "gain")
    maxgain      = cfg.getint(camera_type, "maxgain")
    autogain     = cfg.getboolean(camera_type, "autogain")
    exposure     = cfg.getint(camera_type, "exposure")
    binning      = cfg.getint(camera_type, "bin")
    brightness   = cfg.getint(camera_type, "brightness")
    bandwidth    = cfg.getint(camera_type, "bandwidth")
    high_speed   = cfg.getint(camera_type, "high_speed")
    hardware_bin = cfg.getint(camera_type, "hardware_bin")
    sdk          = cfg.get(camera_type, "sdk")
    try:
        software_bin = cfg.getint(camera_type, "software_bin")
    except configparser.Error:
        software_bin = 0

    # Initialize device
    asi.init(sdk)

    num_cameras = asi.get_num_cameras()
    if num_cameras == 0:
        logger.error("No ZWOASI cameras found")
        raise ValueError
        sys.exit()

    cameras_found = asi.list_cameras()  # Models names of the connected cameras

    if num_cameras == 1:
        device_id = 0
        logger.info("Found one camera: %s" % cameras_found[0])
    else:
        logger.info("Found %d ZWOASI cameras" % num_cameras)
        for n in range(num_cameras):
            logger.info("    %d: %s" % (n, cameras_found[n]))
        logger.info("Using #%d: %s" % (device_id, cameras_found[device_id]))

    camera = asi.Camera(device_id)
    camera_info = camera.get_camera_property()
    logger.debug("ASI Camera info:")
    for (key, value) in camera_info.items():
        logger.debug("  %s : %s" % (key,value))

    camera.set_control_value(asi.ASI_BANDWIDTHOVERLOAD, bandwidth)
    camera.disable_dark_subtract()
    camera.set_control_value(asi.ASI_GAIN, gain, auto=autogain)
    camera.set_control_value(asi.ASI_EXPOSURE, exposure, auto=False)
    camera.set_control_value(asi.ASI_AUTO_MAX_GAIN, maxgain)
    camera.set_control_value(asi.ASI_AUTO_MAX_BRIGHTNESS, 20)
    camera.set_control_value(asi.ASI_WB_B, 99)
    camera.set_control_value(asi.ASI_WB_R, 75)
    camera.set_control_value(asi.ASI_GAMMA, 50)
    camera.set_control_value(asi.ASI_BRIGHTNESS, brightness)
    camera.set_control_value(asi.ASI_FLIP, 0)
    try:
        camera.set_control_value(asi.ASI_HIGH_SPEED_MODE, high_speed)
    except:
        pass
    try:
        camera.set_control_value(asi.ASI_HARDWARE_BIN, hardware_bin)
    except:
        pass
    camera.set_roi(bins=binning)
    camera.start_video_capture()
    camera.set_image_type(asi.ASI_IMG_RAW8)

    try:
        # Fix autogain
        if autogain:
            while True:
                # Get frame
                z = camera.capture_video_frame()

                # Break on no change in gain
                settings = camera.get_control_values()
                if gain == settings["Gain"]:
                    break
                gain = settings["Gain"]
                camera.set_control_value(asi.ASI_GAIN, gain, auto=autogain)

        # Loop until reaching end time
        while float(time.time()) < tend:
            # Wait for available capture buffer to become available
            if (image_queue.qsize() > 1):
                logger.warning("Acquiring data faster than your CPU can process")
                slow_CPU = True
            while (image_queue.qsize() > 1):
                time.sleep(0.1)
            if slow_CPU:
                lost_video = time.time() - t
                logger.info("Waited %.3fs for available capture buffer" % lost_video)
                slow_CPU = False

            # Get settings
            try:
                settings = camera.get_control_values()
                gain = settings["Gain"]
                temp = settings["Temperature"] / 10
            except:
                gain, temp = 0, 0
            logger.info("Capturing frame with gain %d, temperature %.1f" % (gain, temp))

            # Set gain
            if autogain:
                camera.set_control_value(asi.ASI_GAIN, gain, auto=autogain)

            # Get frames
            for i in range(nz):
                # Store start time
                t0 = float(time.time())

                # Get frame
                z = camera.capture_video_frame()

                # Apply software binning
                if software_bin > 1:
                    my, mx = z.shape
                    z = cv2.resize(z, (mx // software_bin, my // software_bin))
                
                # Compute mid time
                t = (float(time.time()) + t0) / 2

                # Display Frame
                if live is True:
                    cv2.imshow("Capture", z)
                    cv2.waitKey(1)

                # Store results
                if first:
                    z1[:, :, i] = z
                    t1[i] = t
                else:
                    z2[:, :, i] = z
                    t2[i] = t

            if first: 
                buf = 1
            else:
                buf = 2
            image_queue.put(buf)
            logger.debug("Captured buffer %d (%dx%dx%d)" % (buf, nx, ny, nz))

            # Swap flag
            first = not first
        reason = "Session complete"
    except KeyboardInterrupt:
        print()
        reason = "Keyboard interrupt"
    except ValueError as e:
        logger.error("%s" % e)
        reason = "Wrong image dimensions? Fix nx, ny in config."
    except MemoryError as e:
        logger.error("Capture: Memory error %s" % e)
    finally:
        # End capture
        logger.info("Capture: %s - Exiting" % reason)
        camera.stop_video_capture()
        camera.close()

# Define SVBony Capture function
#
def _capture_svb_buffer(zbase, tbase, nx, ny, nz,
                        conf_file, device_id, live, buffer_number):
    """
    Capture one complete STVID buffer using a short-lived SVBONY worker.

    IMPORTANT:
        The SV305M Pro / current SVBONY SDK combination used by the
        working zanco implementation returns RGBA8 data from
        PySVB.get_video_data(), i.e. 4 bytes per pixel.

        The SV305M Pro is monochrome. The R channel is therefore used
        as the STVID uint8 image.

    The worker is deliberately short-lived. This prevents SDK/Python
    memory retained by get_video_data() from accumulating across many
    STVID buffers.
    """

    global logger
    logger = setup_logging(os.getcwd())

    cfg = configparser.ConfigParser(
        inline_comment_prefixes=("#", ";")
    )

    if not cfg.read(conf_file):
        raise RuntimeError(
            "Could not read configuration file: %s" % conf_file
        )

    camera_type = "SVB"

    exposure = cfg.getint(
        camera_type,
        "exposure"
    )

    gain = cfg.getint(
        camera_type,
        "gain"
    )

    # Shared STVID destination buffer.
    z = np.ctypeslib.as_array(
        zbase.get_obj()
    ).reshape(ny, nx, nz)

    t = np.ctypeslib.as_array(
        tbase.get_obj()
    )

    camera = None

    try:

        logger.info(
            "SVB worker starting: buffer=%d, %dx%dx%d",
            buffer_number,
            nx,
            ny,
            nz
        )

        # ------------------------------------------------------------
        # Import PySVB inside the worker.
        #
        # This is important because STVID uses multiprocessing spawn.
        # ------------------------------------------------------------

        from pysvb.camera import (
            PySVBCameraSDK,
            SVB_CAMERA_MODE,
            SVB_ROI_FORMAT,
            SVB_CONTROL_TYPE,
        )

        # ------------------------------------------------------------
        # Initialise SDK.
        # ------------------------------------------------------------

        sdk = PySVBCameraSDK()

        logger.info(
            "SVB SDK version: %s",
            sdk.sdk_version
        )

        number_of_cameras = (
            sdk.get_num_of_connected_cameras()
        )

        if number_of_cameras <= 0:
            raise RuntimeError(
                "No SVBONY camera found"
            )

        logger.info(
            "SVB cameras connected: %d",
            number_of_cameras
        )

        if device_id < 0 or device_id >= number_of_cameras:
            raise RuntimeError(
                "Invalid SVB device_id=%d; "
                "%d camera(s) available"
                % (
                    device_id,
                    number_of_cameras
                )
            )

        # ------------------------------------------------------------
        # Camera information.
        # ------------------------------------------------------------

        camera_info = sdk.get_camera_info(
            device_id
        )

        camera_id = camera_info.CameraID

        logger.info(
            "SVB camera: %s",
            camera_info.FriendlyName
        )

        logger.info(
            "SVB camera ID: %s",
            camera_id
        )

        logger.info(
            "SVB serial: %s",
            camera_info.CameraSN
        )

        # ------------------------------------------------------------
        # PySVB is the ONLY owner of the camera.
        #
        # Do NOT use ctypes/SVBOpenCamera here.
        # Do NOT create another SDK handle.
        # ------------------------------------------------------------

        sdk.open_camera(
            camera_id
        )

        # ------------------------------------------------------------
        # Camera properties.
        # ------------------------------------------------------------

        props = sdk.get_camera_property(
            camera_id
        )

        logger.info(
            "SVB sensor: %dx%d",
            props.MaxWidth,
            props.MaxHeight
        )

        logger.info(
            "SVB maximum bit depth: %d",
            props.MaxBitDepth
        )

        logger.info(
            "SVB colour flag: %s",
            props.IsColorCam
        )

        # ------------------------------------------------------------
        # Put camera into normal mode.
        # ------------------------------------------------------------

        mode = sdk.get_camera_mode(
            camera_id
        )

        if mode != SVB_CAMERA_MODE.SVB_MODE_NORMAL:

            logger.info(
                "Changing SVB camera mode to NORMAL"
            )

            sdk.set_camera_mode(
                camera_id,
                SVB_CAMERA_MODE.SVB_MODE_NORMAL
            )

        # ------------------------------------------------------------
        # Configure ROI.
        #
        # IMPORTANT:
        # set_roi_format() expects width/height AFTER binning.
        #
        # Start with BIN 1. We should not introduce hardware binning
        # until basic SV305M Pro acquisition is proven.
        # ------------------------------------------------------------

        roi = SVB_ROI_FORMAT(
            0,
            0,
            int(nx),
            int(ny),
            1
        )

        logger.info(
            "Setting SVB ROI: %dx%d",
            nx,
            ny
        )

        sdk.set_roi_format(
            camera_id,
            roi
        )

        actual_roi = sdk.get_roi_format(
            camera_id
        )

        logger.info(
            "SVB actual ROI: %dx%d bin=%d",
            actual_roi.width,
            actual_roi.height,
            actual_roi.bin
        )

        if (
            int(actual_roi.width) != int(nx)
            or
            int(actual_roi.height) != int(ny)
        ):
            raise RuntimeError(
                "SVB rejected requested ROI: "
                "requested=%dx%d actual=%dx%d"
                % (
                    nx,
                    ny,
                    actual_roi.width,
                    actual_roi.height
                )
            )

        # ------------------------------------------------------------
        # Configure exposure and gain.
        # ------------------------------------------------------------

        if exposure <= 0:
            raise ValueError(
                "Invalid SVB exposure: %d us"
                % exposure
            )

        if gain < 0:
            raise ValueError(
                "Invalid SVB gain: %d"
                % gain
            )

        logger.info(
            "SVB exposure=%d us gain=%d",
            exposure,
            gain
        )

        sdk.set_control_value(
            camera_id,
            SVB_CONTROL_TYPE.SVB_EXPOSURE,
            exposure,
            False
        )

        sdk.set_control_value(
            camera_id,
            SVB_CONTROL_TYPE.SVB_GAIN,
            gain,
            False
        )

        # Disable automatic saving of parameters.
        try:
            sdk.set_autosave_param(
                camera_id,
                False
            )
        except Exception:
            pass

        # ------------------------------------------------------------
        # CRITICAL:
        #
        # Do NOT force RAW8 here.
        #
        # The working SVBONY program demonstrated that
        # get_video_data() returns RGBA8 for this camera/SDK.
        # ------------------------------------------------------------

        bytes_per_pixel = 4

        frame_size = (
            int(nx)
            * int(ny)
            * bytes_per_pixel
        )

        logger.info(
            "SVB expected frame format: RGBA8"
        )

        logger.info(
            "SVB expected frame size: %d bytes",
            frame_size
        )

        # The working program uses a 5000 ms timeout.
        wait_ms = 5000

        # ------------------------------------------------------------
        # Start video.
        # ------------------------------------------------------------

        result = sdk.start_video_capture(
            camera_id
        )

        logger.info(
            "SVB start_video_capture result=%s",
            result
        )

        # ------------------------------------------------------------
        # Reusable output frame.
        # ------------------------------------------------------------

        output_frame = np.empty(
            (int(ny), int(nx)),
            dtype=np.uint8
        )

        # ------------------------------------------------------------
        # Capture nz frames.
        # ------------------------------------------------------------

        for i in range(nz):

            t0 = time.time()

            frame_ok = False

            frame = None

            # The working implementation retries black/invalid frames.
            for attempt in range(6):

                frame = sdk.get_video_data(
                    camera_id,
                    frame_size,
                    wait_ms
                )

                if frame is None:
                    logger.warning(
                        "SVB buffer=%d frame=%d: "
                        "get_video_data returned None "
                        "(attempt %d/6)",
                        buffer_number,
                        i,
                        attempt + 1
                    )
                    continue

                try:
                    raw = np.frombuffer(
                        frame,
                        dtype=np.uint8
                    )
                except TypeError:
                    raw = np.asarray(
                        frame,
                        dtype=np.uint8
                    ).reshape(-1)

                if raw.size < frame_size:

                    logger.warning(
                        "SVB buffer=%d frame=%d: "
                        "short frame %d/%d bytes",
                        buffer_number,
                        i,
                        raw.size,
                        frame_size
                    )

                    continue

                # ----------------------------------------------------
                # Interpret returned data as RGBA8.
                # ----------------------------------------------------

                rgba = raw[
                    :frame_size
                ].reshape(
                    int(ny),
                    int(nx),
                    4
                )

                # The working implementation found R/G/B equivalent
                # for the monochrome SV305M Pro.
                #
                # Use R as the monochrome STVID signal.
                output_frame[:, :] = rgba[:, :, 0]

                # ----------------------------------------------------
                # Reject completely black frames.
                #
                # This is important with the SVBONY SDK because a
                # successful SDK call can occasionally produce a
                # useless frame.
                # ----------------------------------------------------

                if int(output_frame.max()) == 0:

                    logger.warning(
                        "SVB buffer=%d frame=%d: "
                        "black frame, retry %d/6",
                        buffer_number,
                        i,
                        attempt + 1
                    )

                    continue

                frame_ok = True

                if attempt:
                    logger.info(
                        "SVB buffer=%d frame=%d: "
                        "valid frame after %d retries",
                        buffer_number,
                        i,
                        attempt
                    )

                break

            if not frame_ok:

                raise RuntimeError(
                    "SVB buffer=%d frame=%d: "
                    "no valid frame after 6 attempts"
                    % (
                        buffer_number,
                        i
                    )
                )

            # --------------------------------------------------------
            # Ensure dimensions are exactly what STVID expects.
            # --------------------------------------------------------

            if output_frame.shape != (ny, nx):

                output_frame = cv2.resize(
                    output_frame,
                    (nx, ny),
                    interpolation=cv2.INTER_AREA
                )

            # --------------------------------------------------------
            # Live display.
            # --------------------------------------------------------

            if live:

                cv2.imshow(
                    "Capture",
                    output_frame
                )

                cv2.waitKey(1)

            # --------------------------------------------------------
            # Write directly into STVID shared memory.
            # --------------------------------------------------------

            z[:, :, i] = output_frame

            # Midpoint timestamp.
            t[i] = (
                time.time() + t0
            ) / 2.0

            if (i + 1) % 10 == 0:

                logger.info(
                    "SVB worker buffer=%d: "
                    "%d/%d frames",
                    buffer_number,
                    i + 1,
                    nz
                )

            # Explicitly release the temporary SDK objects.
            #
            # The working implementation found that PySVB can retain
            # substantial memory after get_video_data().
            del raw
            del rgba
            del frame

        logger.info(
            "SVB worker buffer=%d complete: %d frames",
            buffer_number,
            nz
        )

    except Exception:

        logger.exception(
            "SVB worker buffer=%d failed",
            buffer_number
        )

        raise

    finally:

        # ------------------------------------------------------------
        # Stop capture.
        # ------------------------------------------------------------

        if camera_id is not None:

            try:
                sdk.stop_video_capture(
                    camera_id
                )
            except Exception:

                logger.exception(
                    "SVB stop_video_capture failed"
                )

            # --------------------------------------------------------
            # IMPORTANT:
            #
            # Only PySVB closes the camera.
            # No native SVBCloseCamera().
            # --------------------------------------------------------

            try:
                sdk.close_camera(
                    camera_id
                )
            except Exception:

                logger.exception(
                    "SVB close_camera failed"
                )

        # Encourage Python to release temporary objects before the
        # worker exits. The worker exit itself is the important part.
        gc.collect()

        logger.info(
            "SVB worker buffer=%d exiting",
            buffer_number
        )


def capture_svb(image_queue,
                z1base, t1base,
                z2base, t2base,
                nx, ny, nz,
                tend,
                device_id,
                live,
                conf_file):
    """
    STVID SVBONY acquisition backend.

    Unlike the ASI backend, SVBONY acquisition is isolated into a
    short-lived worker for each STVID double buffer.

    This is intentional and is based on the proven SV305M Pro
    acquisition implementation.
    """

    global logger
    logger = setup_logging(os.getcwd())

    capture_start = time.time()

    buffer_sequence = 0
    total_frames = 0

    reason = "Unknown"

    logger.info(
        "SVB acquisition start: %.3f -> %.3f",
        capture_start,
        tend
    )

    logger.info(
        "SVB STVID frame size: %dx%d, %d frames/buffer",
        nx,
        ny,
        nz
    )

    try:

        # ------------------------------------------------------------
        # STVID uses the queue to announce which shared buffer is
        # ready. Existing STVID uses 1/2 as the buffer identifiers.
        #
        # We preserve that interface.
        # ------------------------------------------------------------

        first = True

        while time.time() < tend:

            # --------------------------------------------------------
            # Don't overwrite a buffer that the compressor is using.
            #
            # Existing STVID's image_queue contains completed buffers.
            # Therefore wait until fewer than two are outstanding.
            # --------------------------------------------------------

            while image_queue.qsize() > 1:

                time.sleep(0.05)

            # --------------------------------------------------------
            # Select STVID shared buffer.
            # --------------------------------------------------------

            if first:

                buf = 1

                zbase = z1base
                tbase = t1base

            else:

                buf = 2

                zbase = z2base
                tbase = t2base

            buffer_sequence += 1

            logger.info(
                "SVB starting worker: "
                "buffer=%d sequence=%d",
                buf,
                buffer_sequence
            )

            # --------------------------------------------------------
            # IMPORTANT:
            #
            # Start a completely new process for each STVID buffer.
            #
            # This is the key architectural difference from the
            # previous capture_svb() implementation.
            # --------------------------------------------------------

            worker = multiprocessing.Process(
                target=_capture_svb_buffer,
                name="svbony_buffer_%d" % buf,
                args=(
                    zbase,
                    tbase,
                    nx,
                    ny,
                    nz,
                    conf_file,
                    device_id,
                    live,
                    buf
                )
            )

            worker.start()

            worker.join()

            logger.info(
                "SVB worker finished: "
                "buffer=%d pid=%s exitcode=%s",
                buf,
                worker.pid,
                worker.exitcode
            )

            # --------------------------------------------------------
            # A worker failure must stop acquisition rather than
            # allowing STVID to compress an incomplete buffer.
            # --------------------------------------------------------

            if worker.exitcode != 0:

                raise RuntimeError(
                    "SVB worker failed: "
                    "buffer=%d exitcode=%s"
                    % (
                        buf,
                        worker.exitcode
                    )
                )

            total_frames += nz

            # --------------------------------------------------------
            # Tell compressor that this complete buffer is available.
            # --------------------------------------------------------

            image_queue.put(
                buf
            )

            logger.debug(
                "SVB buffer ready: %d "
                "(buffers=%d frames=%d)",
                buf,
                buffer_sequence,
                total_frames
            )

            first = not first

        reason = "Session complete"

    except KeyboardInterrupt:

        reason = "Keyboard interrupt"

    except Exception as e:

        reason = (
            "SVB acquisition error: %s: %s"
            % (
                type(e).__name__,
                e
            )
        )

        logger.exception(
            "%s",
            reason
        )

    finally:

        logger.info(
            "SVB acquisition exit: "
            "reason=%s buffers=%d frames=%d elapsed=%.3f",
            reason,
            buffer_sequence,
            total_frames,
            time.time() - capture_start
        )
# End SVBony capture


def compress(image_queue, z1base, t1base, z2base, t2base, nx, ny, nz, tend, path, device_id, conf_file):
    """ compress: Aggregate nframes of observations into a single FITS file, with statistics.

        ImageHDU[0]: mean pixel value nframes         (zmax)
        ImageHDU[1]: standard deviation of nframes    (zstd)
        ImageHDU[2]: maximum pixel value of nframes   (zmax)
        ImageHDU[3]: maximum pixel value frame number (znum)

    Also updates a [observations_path]/control/state.txt for interfacing with satttools/runsched and sattools/slewto
    """
    global logger
    logger = setup_logging(os.getcwd())

    cfg = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    cfg.read(conf_file)

    z1 = np.ctypeslib.as_array(z1base.get_obj()).reshape(ny, nx, nz)
    t1 = np.ctypeslib.as_array(t1base.get_obj())
    z2 = np.ctypeslib.as_array(z2base.get_obj()).reshape(ny, nx, nz)
    t2 = np.ctypeslib.as_array(t2base.get_obj())
    
    # Force a restart
    controlpath = os.path.join(path, "control")
    if not os.path.exists(controlpath):
        try:
            os.makedirs(controlpath)
        except PermissionError:
            logger.error("Can not create control path directory: %s" % controlpath)
            raise
    if not os.path.exists(os.path.join(controlpath, "position.txt")):
        with open(os.path.join(controlpath, "position.txt"), "w") as fp:
            fp.write("\n")
            
    with open(os.path.join(controlpath, "state.txt"), "w") as fp:
        fp.write("restart\n")

    try:
        # Start processing
        while True:
            # Check mount state
            restart = False
            with open(os.path.join(controlpath, "state.txt"), "r") as fp:
                line = fp.readline().rstrip()
                if line == "restart":
                    restart = True

            # Restart
            if restart:
                # Log state
                with open(os.path.join(controlpath, "state.txt"), "w") as fp:
                    fp.write("observing\n")

                # Get obsid
                trestart = time.gmtime()
                obsid = "%s_%d/%s" % (time.strftime("%Y%m%d", trestart), device_id, time.strftime("%H%M%S", trestart))
                filepath = os.path.join(path, obsid)
                logger.info("Storing files in %s" % filepath)

                # Create output directory
                if not os.path.exists(filepath):
                    try:
                        os.makedirs(filepath)
                    except PermissionError:
                        logger.error("Can not create output directory: %s" % filepath)
                        raise

                # Get mount position
                with open(os.path.join(controlpath, "position.txt"), "r") as fp:
                    line = fp.readline()
                with open(os.path.join(filepath, "position.txt"), "w") as fp:
                    fp.write(line)

            # Wait for completed capture buffer to become available
            while image_queue.empty():
                time.sleep(0.1)
                
            # Get next buffer # from the work queue
            try:
                proc_buffer = image_queue.get(timeout=60)
            except:
                logger.debug("Queue timed out")
                break
            logger.debug("Processing buffer %d" % proc_buffer)

            # Log start time
            tstart = time.time()

            # Process first buffer
            if proc_buffer == 1:
                t = t1                
                z = z1
            elif proc_buffer == 2:
                t = t2
                z = z2

            # Format time
            nfd = "%s.%03d" % (time.strftime("%Y-%m-%dT%T",
                                             time.gmtime(t[0])), int((t[0] - np.floor(t[0])) * 1000))
            t0 = Time(nfd, format="isot")
            dt = t - t[0]

            # Cast to 32 bit float
            z = z.astype("float32")
            
            # Compute statistics
            zmax = np.max(z, axis=2)
            znum = np.argmax(z, axis=2)
            zs1 = np.sum(z, axis=2) - zmax
            zs2 = np.sum(z * z, axis=2) - zmax * zmax 
            zavg = zs1 / float(nz - 1)
            zstd = np.sqrt((zs2 - zs1 * zavg) / float(nz - 2))

            # Convert to float and flip
            zmax = np.flipud(zmax.astype("float32"))
            znum = np.flipud(znum.astype("float32"))
            zavg = np.flipud(zavg.astype("float32"))
            zstd = np.flipud(zstd.astype("float32"))

            # Generate fits
            ftemp = "%s.temp" % nfd.replace(":", "-")
            fname = "%s.fits" % nfd.replace(":", "-")

            # Format header
            hdr = fits.Header()
            hdr["DATE-OBS"] = "%s" % nfd
            hdr["MJD-OBS"]  = t0.mjd
            hdr["EXPTIME"]  = dt[-1] - dt[0]
            hdr["NFRAMES"]  = nz
            hdr["CRPIX1"]   = float(nx) / 2
            hdr["CRPIX2"]   = float(ny) / 2
            hdr["CRVAL1"]   = 0.0
            hdr["CRVAL2"]   = 0.0
            hdr["CD1_1"]    = 1 / 3600
            hdr["CD1_2"]    = 0.0
            hdr["CD2_1"]    = 0.0
            hdr["CD2_2"]    = 1 / 3600
            hdr["CTYPE1"]   = "RA---TAN"
            hdr["CTYPE2"]   = "DEC--TAN"
            hdr["CUNIT1"]   = "deg"
            hdr["CUNIT2"]   = "deg"
            hdr["CRRES1"]   = 0.0
            hdr["CRRES2"]   = 0.0
            hdr["EQUINOX"]  = 2000.0
            hdr["RADECSYS"] = "ICRS"
            hdr["COSPAR"]   = cfg.getint("Observer", "cospar")
            hdr["OBSERVER"] = cfg.get("Observer", "name")
            hdr["SITELONG"] = cfg.getfloat("Observer", "longitude")
            hdr["SITELAT"] = cfg.getfloat("Observer", "latitude")
            hdr["ELEVATIO"] = cfg.getfloat("Observer", "height")
            if cfg.getboolean("Setup", "tracking_mount"):
                hdr["TRACKED"] = 1
            else:
                hdr["TRACKED"] = 0
            for i in range(nz):
                hdr["DT%04d" % i] = dt[i]
            for i in range(10):
                hdr["DUMY%03d" % i] = 0.0

            # Write fits file
            hdu = fits.PrimaryHDU(data=np.array([zavg, zstd, zmax, znum]),
                                  header=hdr)
            hdu.writeto(os.path.join(filepath, ftemp))
            os.rename(os.path.join(filepath, ftemp), os.path.join(filepath, fname))

            logger.info("Compressed %s in %.2f sec" % (fname, time.time() - tstart))

            # Exit on end of capture
            if t[-1] > tend:
                break
            logger.debug("Processed buffer %d" % proc_buffer)
            

    except KeyboardInterrupt:
        pass
    except MemoryError as e:
        logger.error("Compress: Memory error %s" % e)
    finally:
        # Exiting
        logger.info("Exiting compress")


# Main function
if __name__ == '__main__':
    multiprocessing.set_start_method("spawn", force=True)
    
    # Read commandline options
    conf_parser = argparse.ArgumentParser(description="Capture and compress" +
                                                      " live video frames.")
    conf_parser.add_argument("-c", "--conf_file",
                             help="Specify configuration file(s). If no file" +
                             " is specified 'configuration.ini' is used.",
                             action="append",
                             nargs="?",
                             metavar="FILE")
    conf_parser.add_argument("-t", "--test", 
                             nargs="?",
                             action="store", 
                             default=False,
                             help="Testing mode - Start capturing immediately for (optional) seconds",
                             metavar="s")
    conf_parser.add_argument("-l", "--live", action="store_true",
                             help="Display live image while capturing")

    args = conf_parser.parse_args()

    # Process commandline options and parse configuration
    cfg = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    
    conf_file = args.conf_file if args.conf_file else "configuration.ini"
    result = cfg.read(conf_file)

    if not result:
        print("Could not read config file: %s\nExiting..." % conf_file)
        sys.exit()

    # Setup logging
    logFormatter = logging.Formatter("%(asctime)s [%(threadName)-12.12s] " +
                                     "[%(levelname)-5.5s]  %(message)s")
    logger = logging.getLogger()

    # Generate directory
    path = os.path.abspath(cfg.get("Setup", "observations_path"))
    if not os.path.exists(path):
        try:
            os.makedirs(path)
        except PermissionError:
            logger.error("Can not create observations_path: %s" % path)
            sys.exit()

    fileHandler = logging.FileHandler(os.path.join(path, "acquire.log"))
    fileHandler.setFormatter(logFormatter)
    logger.addHandler(fileHandler)

    consoleHandler = logging.StreamHandler(sys.stdout)
    consoleHandler.setFormatter(logFormatter)
    logger.addHandler(consoleHandler)
    logger.setLevel(logging.DEBUG)

    logger.info("Using config: %s" % conf_file)

    # Testing mode
    if args.test is None:
        test_duration = 31
        testing = True
    elif args.test is not False:
        test_duration = int(args.test)
        testing = True
    else:
        testing = False
    logger.info("Test mode: %s" % testing)
    if (testing):
        logger.info("Test duration: %ds" % test_duration)

    # Live mode
    live = True if args.live else False
    logger.info("Live mode: %s" % live)

    # Get camera type
    camera_type = cfg.get("Setup", "camera_type")

    # Get device id
    device_id = cfg.getint(camera_type, "device_id")

    # Current time
    tnow = Time.now()

    # Set location
    loc = EarthLocation(lat=cfg.getfloat("Observer", "latitude") * u.deg,
                        lon=cfg.getfloat("Observer", "longitude") * u.deg,
                        height=cfg.getfloat("Observer", "height") * u.m)

    if not testing:
        # Reference altitudes
        refalt_set  = cfg.getfloat("Setup", "alt_sunset") * u.deg
        refalt_rise = cfg.getfloat("Setup", "alt_sunrise") * u.deg

        # Aimpoint configuration
        if cfg.has_section("Aimpoint"):
            aimpoint_az = cfg.getfloat("Aimpoint", "az_deg") * u.deg
            aimpoint_alt = cfg.getfloat("Aimpoint", "alt_deg") * u.deg
            aimpoint_height = cfg.getfloat("Aimpoint", "height_km") * u.km
        else:
            aimpoint_az, aimpoint_alt, aimpoint_height = None, None, None

        # Get logic
        action, wait_time, tend, state = observe_logic(tnow, loc, refalt_set, refalt_rise,
                                                       aimpoint_az, aimpoint_alt, aimpoint_height)

        # Wait for observation start
        logger.info(state)
        if action == "wait":
            logger.info(f"Waiting for {wait_time:.0f} seconds.")
            try:
                time.sleep(wait_time)
            except KeyboardInterrupt:
                sys.exit()
    else:
        tend = tnow + test_duration * u.s

    # Read shutter config
    if cfg.has_section("Shutter"):
        from stvid.shutter import Shutter
        shutter = Shutter(cfg.getint("Shutter", "pin"))
    else:
        shutter = None
        
    logger.info("Starting data acquisition")
    logger.info("Acquisition will end after "+tend.isot)

    # Get settings
    nx = cfg.getint(camera_type, "nx")
    ny = cfg.getint(camera_type, "ny")
    nz = cfg.getint(camera_type, "nframes")

    # Initialize arrays
    z1base = multiprocessing.Array(ctypes.c_uint8, nx * ny * nz)
    t1base = multiprocessing.Array(ctypes.c_double, nz)
    z2base = multiprocessing.Array(ctypes.c_uint8, nx * ny * nz)
    t2base = multiprocessing.Array(ctypes.c_double, nz)

    image_queue = multiprocessing.Queue()

    # Set processes
    pcompress = multiprocessing.Process(target=compress,
                                        name="compress",
                                        args=(image_queue,
                                              z1base, t1base, z2base, t2base,
                                              nx, ny, nz, tend.unix,
                                              path, device_id, conf_file))
    if camera_type == "PI":
        pcapture = multiprocessing.Process(target=capture_pi,
                                           name="capture_pi",
                                           args=(image_queue,
                                                 z1base, t1base, z2base, t2base,
                                                 nx, ny, nz, tend.unix,
                                                 device_id, live, conf_file))
    elif camera_type == "CV2":
        pcapture = multiprocessing.Process(target=capture_cv2,
                                           name="capture_cv2",
                                           args=(image_queue,
                                                 z1base, t1base, z2base, t2base,
                                                 nx, ny, nz, tend.unix,
                                                 device_id, live, conf_file))
    elif camera_type == "ASI":
        pcapture = multiprocessing.Process(target=capture_asi,
                                           name="capture_asi",
                                           args=(image_queue,
                                                 z1base, t1base, z2base, t2base,
                                                 nx, ny, nz, tend.unix,
                                                 device_id, live, conf_file))

    elif camera_type == "SVB":
        pcapture = multiprocessing.Process(target=capture_svb,
                                           name="capture_svb",
                                           args=(image_queue,
                                                 z1base, t1base, z2base, t2base,
                                                 nx, ny, nz, tend.unix,
                                                 device_id, live, conf_file))

    try:
        # Open shutter
        if shutter:
            shutter.open()
        
        # Start
        pcapture.start()
        pcompress.start()

        # End
        try:
            pcapture.join()
            pcompress.join()
        except (KeyboardInterrupt, ValueError):
            time.sleep(0.1) # Allow a little time for a graceful exit
        except MemoryError as e:
            logger.error("Memory error %s" % e)
        finally:
            pcapture.terminate()
            pcompress.terminate()

        # Release device
        if live is True:
            cv2.destroyAllWindows()
    finally:
        if shutter:
            shutter.close()
