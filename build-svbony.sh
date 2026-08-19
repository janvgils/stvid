#!/bin/bash

# ./build-svbony.sh software/SVBCameraSDK

set -e

if [ "$#" -ne 1 ]; then
    echo "Usage:"
    echo "  $0 /path/to/SVBCameraSDK"
    exit 1
fi

SDK="$1"

if [ ! -f "$SDK/include/SVBCameraSDK.h" ]; then
    echo "Could not find:"
    echo "  $SDK/include/SVBCameraSDK.h"
    exit 1
fi

ARCH=$(uname -m)

case "$ARCH" in
    x86_64)
        SDK_LIB="$SDK/lib/x64"
        ;;
    aarch64)
        SDK_LIB="$SDK/lib/armv8"
        ;;
    armv7l)
        SDK_LIB="$SDK/lib/armv7"
        ;;
    *)
        echo "Unsupported architecture: $ARCH"
        exit 1
        ;;
esac

if [ ! -d "$SDK_LIB" ]; then
    echo "Could not find SDK library directory:"
    echo "  $SDK_LIB"
    exit 1
fi

echo "Architecture : $ARCH"
echo "SDK           : $SDK"
echo "SDK library   : $SDK_LIB"

gcc \
    -shared \
    -fPIC \
    -O2 \
    -Wall \
    -Wextra \
    -I"$SDK/include" \
    -L"$SDK_LIB" \
    -Wl,-rpath,"$SDK_LIB" \
    -o stvid/libstvid_svbony.so \
    stvid/svbony_sdk.c \
    -lSVBCameraSDK \
    -lusb-1.0

echo
echo "Built:"
echo "  stvid/libstvid_svbony.so"
