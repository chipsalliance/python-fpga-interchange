#!/bin/bash

export RAPIDWRIGHT_PATH="$GITHUB_WORKSPACE/env/RapidWright"

# Create the device resource for the test part.
pushd "$GITHUB_WORKSPACE/env"
"$RAPIDWRIGHT_PATH/scripts/invoke_rapidwright.sh" \
    com.xilinx.rapidwright.interchange.DeviceResourcesExample \
    xc7a50tfgg484-1
popd

export CAPNP_PATH="$GITHUB_WORKSPACE/env/capnproto-java/compiler/src/main/schema/"
export INTERCHANGE_SCHEMA_PATH="$GITHUB_WORKSPACE/env/fpga-interchange-schema/interchange"
export DEVICE_RESOURCE_PATH="$GITHUB_WORKSPACE/env"

make test-py
RESULT=$?
if [ $RESULT -ne 0 ]; then
    exit $RESULT
fi
test $(git status --porcelain | wc -l) -eq 0 || { git diff; false; }
