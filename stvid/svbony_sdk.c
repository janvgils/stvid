#include <stdio.h>
#include <stdlib.h>

#include "SVBCameraSDK.h"


/*
 * The Python/API-facing camera number is the connected-camera index.
 *
 * SVBONY uses two identifiers:
 *
 *   index    : 0, 1, ... used by SVBGetCameraInfo()
 *   CameraID : actual SDK ID used by all other camera operations
 *
 * Keep the conversion inside this C wrapper so Python does not need
 * to know about this SDK peculiarity.
 */
static int get_camera_id(int camera_index)
{
    SVB_CAMERA_INFO info;
    SVB_ERROR_CODE result;

    result = SVBGetCameraInfo(
        &info,
        camera_index
    );

    if (result != SVB_SUCCESS)
        return -1;

    return info.CameraID;
}


/*
 * Return the number of connected SVBONY cameras.
 */
int stvid_svbony_num_cameras(void)
{
    return SVBGetNumOfConnectedCameras();
}


/*
 * Open and configure a camera.
 *
 * camera_index is the connected-camera index, NOT CameraID.
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
        "SVBONY: SVBSetROIFormat(%d, %d, %d) = %d\n",
        width,
        height,
        1,
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
     * We want monochrome 8-bit frames.
     */
    result = SVBSetOutputImageType(
        camera_id,
        SVB_IMG_RAW8
    );

    fprintf(
        stderr,
        "SVBONY: SVBSetOutputImageType(RAW8) = %d\n",
        result
    );

    if (result != SVB_SUCCESS)
        goto error_close;


    /*
     * Exposure.
     *
     * The SDK uses long for the value.
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
     * Start streaming.
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

    SVBCloseCamera(camera_id);

    return result;
}


/*
 * Get one frame.
 */
int stvid_svbony_get_frame(
    int camera_index,
    unsigned char *buffer,
    long buffer_size,
    int timeout_ms)
{
    int camera_id;

    camera_id = get_camera_id(camera_index);

    if (camera_id < 0)
        return SVB_ERROR_INVALID_INDEX;

    return SVBGetVideoData(
        camera_id,
        buffer,
        buffer_size,
        timeout_ms
    );
}


/*
 * Stop video capture.
 */
int stvid_svbony_stop(int camera_index)
{
    int camera_id;

    camera_id = get_camera_id(camera_index);

    if (camera_id < 0)
        return SVB_ERROR_INVALID_INDEX;

    return SVBStopVideoCapture(camera_id);
}


/*
 * Close camera.
 */
int stvid_svbony_close(int camera_index)
{
    int camera_id;

    camera_id = get_camera_id(camera_index);

    if (camera_id < 0)
        return SVB_ERROR_INVALID_INDEX;

    return SVBCloseCamera(camera_id);
}


/*
 * Number of dropped frames.
 */
int stvid_svbony_dropped_frames(int camera_index)
{
    int camera_id;
    int dropped = 0;

    camera_id = get_camera_id(camera_index);

    if (camera_id < 0)
        return -1;

    if (SVBGetDroppedFrames(
            camera_id,
            &dropped
        ) != SVB_SUCCESS)
        return -1;

    return dropped;
}
