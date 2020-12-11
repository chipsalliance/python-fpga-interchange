#!/bin/bash

export CAPNP_PATH="$GITHUB_WORKSPACE/capnproto-java/compiler/src/main/schema/"
export INTERCHANGE_SCHEMA_PATH="$GITHUB_WORKSPACE/RapidWright/interchange"
export RAPIDWRIGHT_PATH="$GITHUB_WORKSPACE/RapidWright"

# Create the device resource for the test part.
pushd "$GITHUB_WORKSPACE" && \
    "$RAPIDWRIGHT_PATH/scripts/invoke_rapidwright.sh" \
    com.xilinx.rapidwright.interchange.DeviceResourcesExample \
    xc7a50tfgg484-1 && popd
export DEVICE_RESOURCE_PATH="$GITHUB_WORKSPACE"
make test-py
test $(git status --porcelain | wc -l) -eq 0 || { git diff; false; }
