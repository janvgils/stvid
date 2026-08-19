#include <stdio.h>
#include <stdlib.h>

#include "SVBCameraSDK.h"


/*
 * Return values exposed to Python.
 *
 * 0 = success
 * non-zero = SVBONY SDK error
 */


/*
 * Open and configure camera.
 *
 * SV305M Pro:
 *   1920 x 1080
 *   monochrome
 *   RAW8
 */
int stvid_svbony_open(
    int camera_id,
    int width,
    int height,
    long exposure,
    long gain)
{
    int result;

    int cameras = SVBGetNumOfConnectedCameras();

    if (cameras <= 0)
        return -1000;

    if (camera_id < 0 || camera_id >= cameras)
        return -1001;

    result = SVBOpenCamera(camera_id);

    if (result != SVB_SUCCESS)
        return result;


    /*
     * Set ROI.
     *
     * x = 0
     * y = 0
     * width/height = configured STVID frame
     * binning = 1
     */
    result = SVBSetROIFormat(
        camera_id,
        0,
        0,
        width,
        height,
        1
    );

    if (result != SVB_SUCCESS)
        goto error_close;


    /*
     * Normal continuous capture mode.
     */
    result = SVBSetCameraMode(
        camera_id,
        SVB_MODE_NORMAL
    );

    if (result != SVB_SUCCESS)
        goto error_close;


    /*
     * SV305M Pro is monochrome.
     *
     * RAW8 gives one byte per pixel and therefore fits
     * directly into the existing STVID uint8 shared buffers.
     */
    result = SVBSetOutputImageType(
        camera_id,
        SVB_IMG_RAW8
    );

    if (result != SVB_SUCCESS)
        goto error_close;


    /*
     * Manual exposure.
     */
    result = SVBSetControlValue(
        camera_id,
        SVB_EXPOSURE,
        exposure,
        SVB_FALSE
    );

    if (result != SVB_SUCCESS)
        goto error_close;


    /*
     * Manual gain.
     */
    result = SVBSetControlValue(
        camera_id,
        SVB_GAIN,
        gain,
        SVB_FALSE
    );

    if (result != SVB_SUCCESS)
        goto error_close;


    /*
     * Disable automatic parameter persistence.
     *
     * STVID should control the acquisition explicitly.
     */
    SVBSetAutoSaveParam(camera_id, SVB_FALSE);


    /*
     * Start streaming.
     */
    result = SVBStartVideoCapture(camera_id);

    if (result != SVB_SUCCESS)
        goto error_close;

    return 0;


error_close:

    SVBCloseCamera(camera_id);
    return result;
}


/*
 * Get one frame.
 */
int stvid_svbony_get_frame(
    int camera_id,
    void *buffer,
    long buffer_size,
    int timeout_ms)
{
    return SVBGetVideoData(
        camera_id,
        buffer,
        buffer_size,
        timeout_ms
    );
}


/*
 * Stop streaming.
 */
int stvid_svbony_stop(int camera_id)
{
    return SVBStopVideoCapture(camera_id);
}


/*
 * Close camera.
 */
int stvid_svbony_close(int camera_id)
{
    return SVBCloseCamera(camera_id);
}


/*
 * Number of connected cameras.
 */
int stvid_svbony_num_cameras(void)
{
    return SVBGetNumOfConnectedCameras();
}


/*
 * Number of dropped frames.
 */
int stvid_svbony_dropped_frames(int camera_id)
{
    int dropped = 0;

    if (SVBGetDroppedFrames(camera_id, &dropped) != SVB_SUCCESS)
        return -1;

    return dropped;
}
