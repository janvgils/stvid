#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "SVBCameraSDK.h"


#define STVID_SVBONY_MAX_CAMERAS 16


typedef struct
{
    int camera_id;

    int opened;
    int capturing;

    int width;
    int height;
    int bin;

    SVB_IMG_TYPE image_type;

    /*
     * Bytes per pixel in the output buffer.
     *
     * Y8  = 1
     * Y16 = 2
     */
    int bytes_per_pixel;

    SVB_CAMERA_PROPERTY property;

} STVID_SVBONY_CAMERA;


static STVID_SVBONY_CAMERA cameras[
    STVID_SVBONY_MAX_CAMERAS
];


static int
valid_index(int index)
{
    return index >= 0 &&
           index < STVID_SVBONY_MAX_CAMERAS;
}


static int
find_camera_id(int camera_index)
{
    SVB_CAMERA_INFO info;

    SVB_ERROR_CODE result;


    if (!valid_index(camera_index))
        return -1;


    memset(
        &info,
        0,
        sizeof(info)
    );


    result = SVBGetCameraInfo(
        &info,
        camera_index
    );


    if (result != SVB_SUCCESS)
        return -1;


    return info.CameraID;
}


/*
 * Check whether a particular output format is reported
 * by the camera.
 */
static int
supports_format(
    SVB_CAMERA_PROPERTY *property,
    SVB_IMG_TYPE format)
{
    int i;


    for (i = 0; i < 8; i++) {

        if (property->SupportedVideoFormat[i] == SVB_IMG_END)
            break;

        if (property->SupportedVideoFormat[i] == format)
            return 1;
    }


    return 0;
}


/*
 * Select the best format for STVID.
 *
 * For a monochrome camera:
 *
 *   prefer Y8
 *   otherwise Y16
 *
 * We deliberately do NOT use RAW8.
 *
 * RAW8 is Bayer data and is inappropriate for the
 * monochrome SV305M Pro.
 */
static int
select_image_format(
    SVB_CAMERA_PROPERTY *property,
    SVB_IMG_TYPE *format,
    int *bytes_per_pixel)
{
    if (property->IsColorCam) {

        /*
         * Current implementation is intentionally
         * monochrome-first.
         *
         * This can be extended later for RGB cameras.
         */
        if (supports_format(
                property,
                SVB_IMG_RGB24)) {

            *format = SVB_IMG_RGB24;
            *bytes_per_pixel = 3;

            return 0;
        }

        return -1;
    }


    /*
     * Prefer Y8.
     */
    if (supports_format(
            property,
            SVB_IMG_Y8)) {

        *format = SVB_IMG_Y8;
        *bytes_per_pixel = 1;

        return 0;
    }


    /*
     * Fall back to Y16.
     */
    if (supports_format(
            property,
            SVB_IMG_Y16)) {

        *format = SVB_IMG_Y16;
        *bytes_per_pixel = 2;

        return 0;
    }


    return -1;
}


/*
 * Return number of connected cameras.
 */
int
stvid_svbony_num_cameras(void)
{
    return SVBGetNumOfConnectedCameras();
}


/*
 * Return selected frame width.
 */
int
stvid_svbony_width(int camera_index)
{
    if (!valid_index(camera_index))
        return 0;

    return cameras[camera_index].width;
}


/*
 * Return selected frame height.
 */
int
stvid_svbony_height(int camera_index)
{
    if (!valid_index(camera_index))
        return 0;

    return cameras[camera_index].height;
}


/*
 * Return bytes per pixel.
 */
int
stvid_svbony_bytes_per_pixel(int camera_index)
{
    if (!valid_index(camera_index))
        return 0;

    return cameras[camera_index].bytes_per_pixel;
}


/*
 * Return selected SVB image type.
 */
int
stvid_svbony_image_type(int camera_index)
{
    if (!valid_index(camera_index))
        return -1;

    return (int)cameras[camera_index].image_type;
}


/*
 * Return actual SVB CameraID.
 */
int
stvid_svbony_camera_id(int camera_index)
{
    if (!valid_index(camera_index))
        return -1;

    return cameras[camera_index].camera_id;
}


/*
 * Open and configure camera.
 */
int
stvid_svbony_open(
    int camera_index,
    int requested_width,
    int requested_height,
    long exposure,
    long gain)
{
    int camera_id;

    int width;
    int height;

    int bytes_per_pixel;

    SVB_IMG_TYPE image_type;

    SVB_ERROR_CODE result;

    SVB_CAMERA_PROPERTY property;


    if (!valid_index(camera_index))
        return SVB_ERROR_INVALID_INDEX;


    memset(
        &cameras[camera_index],
        0,
        sizeof(STVID_SVBONY_CAMERA)
    );


    /*
     * Resolve connected-camera index -> CameraID.
     *
     * This is done ONCE.
     */
    camera_id = find_camera_id(
        camera_index
    );


    fprintf(
        stderr,
        "SVBONY: camera index %d -> CameraID %d\n",
        camera_index,
        camera_id
    );


    if (camera_id < 0)
        return SVB_ERROR_INVALID_INDEX;


    /*
     * Open camera.
     */
    result = SVBOpenCamera(
        camera_id
    );


    fprintf(
        stderr,
        "SVBONY: SVBOpenCamera(%d) = %d\n",
        camera_id,
        result
    );


    if (result != SVB_SUCCESS)
        return result;


    cameras[camera_index].camera_id = camera_id;
    cameras[camera_index].opened = 1;


    /*
     * Read actual camera capabilities.
     */
    memset(
        &property,
        0,
        sizeof(property)
    );


    result = SVBGetCameraProperty(
        camera_id,
        &property
    );


    fprintf(
        stderr,
        "SVBONY: SVBGetCameraProperty() = %d\n",
        result
    );


    if (result != SVB_SUCCESS)
        goto error_close;


    cameras[camera_index].property =
        property;


    fprintf(
        stderr,
        "SVBONY: sensor %ld x %ld\n",
        property.MaxWidth,
        property.MaxHeight
    );


    fprintf(
        stderr,
        "SVBONY: color=%d bitdepth=%d\n",
        property.IsColorCam,
        property.MaxBitDepth
    );


    /*
     * Select actual output format.
     */
    if (select_image_format(
            &property,
            &image_type,
            &bytes_per_pixel) != 0) {

        fprintf(
            stderr,
            "SVBONY: no supported output format\n"
        );

        result = SVB_ERROR_INVALID_IMGTYPE;

        goto error_close;
    }


    cameras[camera_index].image_type =
        image_type;

    cameras[camera_index].bytes_per_pixel =
        bytes_per_pixel;


    fprintf(
        stderr,
        "SVBONY: selected image type %d, %d bytes/pixel\n",
        (int)image_type,
        bytes_per_pixel
    );


    /*
     * Determine dimensions.
     *
     * The SV305M Pro reports 1920x1080.
     *
     * For now we accept a requested ROI only if it
     * fits inside the sensor.
     *
     * STVID normally supplies 1920x1080.
     */
    width = requested_width;

    height = requested_height;


    if (width <= 0)
        width = (int)property.MaxWidth;

    if (height <= 0)
        height = (int)property.MaxHeight;


    if (width > property.MaxWidth)
        width = (int)property.MaxWidth;

    if (height > property.MaxHeight)
        height = (int)property.MaxHeight;


    /*
     * Use bin 1 for the normal STVID stream.
     */
    cameras[camera_index].bin = 1;

    cameras[camera_index].width = width;
    cameras[camera_index].height = height;


    /*
     * Set ROI.
     */
    result = SVBSetROIFormat(
        camera_id,
        0,
        0,
        width,
        height,
        1
    );


    fprintf(
        stderr,
        "SVBONY: SVBSetROIFormat(%d, %d, 1) = %d\n",
        width,
        height,
        result
    );


    if (result != SVB_SUCCESS)
        goto error_close;


    /*
     * Normal continuous video mode.
     */
    result = SVBSetCameraMode(
        camera_id,
        SVB_MODE_NORMAL
    );


    fprintf(
        stderr,
        "SVBONY: SVBSetCameraMode(NORMAL) = %d\n",
        result
    );


    if (result != SVB_SUCCESS)
        goto error_close;


    /*
     * Set the format actually supported by the camera.
     */
    result = SVBSetOutputImageType(
        camera_id,
        image_type
    );


    fprintf(
        stderr,
        "SVBONY: SVBSetOutputImageType(%d) = %d\n",
        (int)image_type,
        result
    );


    if (result != SVB_SUCCESS)
        goto error_close;


    /*
     * Exposure.
     *
     * SVB exposure is expressed in microseconds.
     */
    result = SVBSetControlValue(
        camera_id,
        SVB_EXPOSURE,
        exposure,
        SVB_FALSE
    );


    fprintf(
        stderr,
        "SVBONY: SVBSetControlValue(EXPOSURE, %ld) = %d\n",
        exposure,
        result
    );


    if (result != SVB_SUCCESS)
        goto error_close;


    /*
     * Gain.
     *
     * The SV305M Pro has gain 1-30 according to
     * the camera specifications.
     *
     * The SDK clamps values outside its supported range.
     */
    result = SVBSetControlValue(
        camera_id,
        SVB_GAIN,
        gain,
        SVB_FALSE
    );


    fprintf(
        stderr,
        "SVBONY: SVBSetControlValue(GAIN, %ld) = %d\n",
        gain,
        result
    );


    if (result != SVB_SUCCESS)
        goto error_close;


    /*
     * Start continuous capture.
     */
    result = SVBStartVideoCapture(
        camera_id
    );


    fprintf(
        stderr,
        "SVBONY: SVBStartVideoCapture() = %d\n",
        result
    );


    if (result != SVB_SUCCESS)
        goto error_close;


    cameras[camera_index].capturing = 1;


    fprintf(
        stderr,
        "SVBONY: camera successfully configured\n"
    );


    return SVB_SUCCESS;


error_close:

    cameras[camera_index].capturing = 0;
    cameras[camera_index].opened = 0;

    SVBCloseCamera(
        camera_id
    );

    cameras[camera_index].camera_id = 0;


    return result;
}


/*
 * Get one frame.
 */
int
stvid_svbony_get_frame(
    int camera_index,
    unsigned char *buffer,
    long buffer_size,
    int timeout_ms)
{
    int camera_id;

    long required_size;


    if (!valid_index(camera_index))
        return SVB_ERROR_INVALID_INDEX;


    if (!cameras[camera_index].opened)
        return SVB_ERROR_CAMERA_CLOSED;


    if (!cameras[camera_index].capturing)
        return SVB_ERROR_INVALID_SEQUENCE;


    if (buffer == NULL)
        return SVB_ERROR_BUFFER_TOO_SMALL;


    camera_id =
        cameras[camera_index].camera_id;


    required_size =
        (long)cameras[camera_index].width *
        (long)cameras[camera_index].height *
        (long)cameras[camera_index].bytes_per_pixel;


    if (buffer_size < required_size) {

        fprintf(
            stderr,
            "SVBONY: buffer too small: "
            "%ld < %ld\n",
            buffer_size,
            required_size
        );

        return SVB_ERROR_BUFFER_TOO_SMALL;
    }


    return SVBGetVideoData(
        camera_id,
        buffer,
        required_size,
        timeout_ms
    );
}


/*
 * Stop capture.
 */
int
stvid_svbony_stop(
    int camera_index)
{
    int camera_id;

    SVB_ERROR_CODE result;


    if (!valid_index(camera_index))
        return SVB_ERROR_INVALID_INDEX;


    if (!cameras[camera_index].opened)
        return SVB_SUCCESS;


    if (!cameras[camera_index].capturing)
        return SVB_SUCCESS;


    camera_id =
        cameras[camera_index].camera_id;


    result = SVBStopVideoCapture(
        camera_id
    );


    cameras[camera_index].capturing = 0;


    return result;
}


/*
 * Close camera.
 */
int
stvid_svbony_close(
    int camera_index)
{
    int camera_id;

    SVB_ERROR_CODE result;


    if (!valid_index(camera_index))
        return SVB_ERROR_INVALID_INDEX;


    if (!cameras[camera_index].opened)
        return SVB_SUCCESS;


    camera_id =
        cameras[camera_index].camera_id;


    /*
     * Stop capture before closing.
     */
    if (cameras[camera_index].capturing) {

        SVBStopVideoCapture(
            camera_id
        );

        cameras[camera_index].capturing = 0;
    }


    result = SVBCloseCamera(
        camera_id
    );


    memset(
        &cameras[camera_index],
        0,
        sizeof(STVID_SVBONY_CAMERA)
    );


    return result;
}


/*
 * Dropped frames.
 */
int
stvid_svbony_dropped_frames(
    int camera_index)
{
    int dropped = 0;

    int camera_id;


    if (!valid_index(camera_index))
        return -1;


    if (!cameras[camera_index].opened)
        return -1;


    camera_id =
        cameras[camera_index].camera_id;


    if (SVBGetDroppedFrames(
            camera_id,
            &dropped) != SVB_SUCCESS)
        return -1;


    return dropped;
}
