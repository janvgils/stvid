#include <stdio.h>
#include <string.h>

#include "SVBCameraSDK.h"


#define STVID_SVBONY_MAX_CAMERAS 16


/*
 * SVBONY distinguishes between:
 *
 *   camera index = position in the connected-camera list
 *   CameraID     = actual SDK camera identifier
 *
 * We resolve the CameraID once when opening the camera and cache it.
 * We must NOT call SVBGetCameraInfo() for every video frame.
 */
static int camera_ids[STVID_SVBONY_MAX_CAMERAS];
static int camera_open[STVID_SVBONY_MAX_CAMERAS];


/*
 * Convert connected-camera index to SVBONY CameraID.
 */
static int get_camera_id(int camera_index)
{
    SVB_CAMERA_INFO info;
    SVB_ERROR_CODE result;

    if (camera_index < 0 ||
        camera_index >= STVID_SVBONY_MAX_CAMERAS)
        return -1;

    result = SVBGetCameraInfo(
        &info,
        camera_index
    );

    if (result != SVB_SUCCESS)
        return -1;

    return info.CameraID;
}


/*
 * Number of connected cameras.
 */
int stvid_svbony_num_cameras(void)
{
    return SVBGetNumOfConnectedCameras();
}


/*
 * Open and configure camera.
 */
int stvid_svbony_open(
    int camera_index,
    int width,
    int height,
    long exposure,
    long gain)
{
    int camera_id;
    SVB_ERROR_CODE result;

    if (camera_index < 0 ||
        camera_index >= STVID_SVBONY_MAX_CAMERAS)
        return SVB_ERROR_INVALID_INDEX;


    /*
     * Resolve CameraID exactly once.
     */
    camera_id = get_camera_id(camera_index);

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
    result = SVBOpenCamera(camera_id);

    fprintf(
        stderr,
        "SVBONY: SVBOpenCamera(%d) = %d\n",
        camera_id,
        result
    );

    if (result != SVB_SUCCESS)
        return result;


    /*
     * Cache CameraID.
     *
     * From this point on all video operations use the cached ID
     * and do NOT call SVBGetCameraInfo() again.
     */
    camera_ids[camera_index] = camera_id;
    camera_open[camera_index] = 1;


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
     * Normal video mode.
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
     * RAW8 output.
     */
    result = SVBSetOutputImageType(
        camera_id,
        SVB_IMG_Y8
    );

    fprintf(
        stderr,
        "SVBONY: SVBSetOutputImageType(Y8) = %d\n",
        result
    );

    if (result != SVB_SUCCESS)
        goto error_close;


    /*
     * Exposure.
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
     * Start capture.
     */
    result = SVBStartVideoCapture(camera_id);

    fprintf(
        stderr,
        "SVBONY: SVBStartVideoCapture() = %d\n",
        result
    );

    if (result != SVB_SUCCESS)
        goto error_close;


    fprintf(
        stderr,
        "SVBONY: camera successfully configured\n"
    );

    return SVB_SUCCESS;


error_close:

    camera_open[camera_index] = 0;
    camera_ids[camera_index] = 0;

    SVBCloseCamera(camera_id);

    return result;
}


/*
 * Get one frame.
 *
 * IMPORTANT:
 * Use the cached CameraID.
 * Do not call SVBGetCameraInfo() while capturing.
 */
int stvid_svbony_get_frame(
    int camera_index,
    unsigned char *buffer,
    long buffer_size,
    int timeout_ms)
{
    int camera_id;

    if (camera_index < 0 ||
        camera_index >= STVID_SVBONY_MAX_CAMERAS)
        return SVB_ERROR_INVALID_INDEX;

    if (!camera_open[camera_index])
        return SVB_ERROR_CAMERA_CLOSED;

    if (buffer == NULL)
        return SVB_ERROR_BUFFER_TOO_SMALL;

    camera_id = camera_ids[camera_index];

    return SVBGetVideoData(
        camera_id,
        buffer,
        buffer_size,
        timeout_ms
    );
}


/*
 * Stop capture.
 */
int stvid_svbony_stop(int camera_index)
{
    int camera_id;

    if (camera_index < 0 ||
        camera_index >= STVID_SVBONY_MAX_CAMERAS)
        return SVB_ERROR_INVALID_INDEX;

    if (!camera_open[camera_index])
        return SVB_ERROR_CAMERA_CLOSED;

    camera_id = camera_ids[camera_index];

    return SVBStopVideoCapture(
        camera_id
    );
}


/*
 * Close camera.
 */
int stvid_svbony_close(int camera_index)
{
    int camera_id;
    SVB_ERROR_CODE result;

    if (camera_index < 0 ||
        camera_index >= STVID_SVBONY_MAX_CAMERAS)
        return SVB_ERROR_INVALID_INDEX;

    if (!camera_open[camera_index])
        return SVB_SUCCESS;

    camera_id = camera_ids[camera_index];

    result = SVBCloseCamera(
        camera_id
    );

    camera_open[camera_index] = 0;
    camera_ids[camera_index] = 0;

    return result;
}


/*
 * Number of dropped frames.
 */
int stvid_svbony_dropped_frames(int camera_index)
{
    int camera_id;
    int dropped = 0;

    if (camera_index < 0 ||
        camera_index >= STVID_SVBONY_MAX_CAMERAS)
        return -1;

    if (!camera_open[camera_index])
        return -1;

    camera_id = camera_ids[camera_index];

    if (SVBGetDroppedFrames(
            camera_id,
            &dropped
        ) != SVB_SUCCESS)
        return -1;

    return dropped;
}
