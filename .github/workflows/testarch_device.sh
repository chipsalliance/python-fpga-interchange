#!/bin/bash

export INTERCHANGE_SCHEMA_PATH="$GITHUB_WORKSPACE/env/fpga-interchange-schema/interchange"
export CAPNP_PATH="$GITHUB_WORKSPACE/env/capnproto-java/compiler/src/main/schema/"

python3 fpga_interchange/testarch_generators/generate_testarch.py --schema_dir $INTERCHANGE_SCHEMA_PATH
mv device_resources.device.gz $GITHUB_WORKSPACE/env
python3 fpga_interchange/nextpnr_emit.py --schema_dir $INTERCHANGE_SCHEMA_PATH --output_dir $GITHUB_WORKSPACE/env --device_config test_data/gen_device_config.yaml --device $GITHUB_WORKSPACE/env/device_resources.device.gz

test $(git status --porcelain | wc -l) -eq 0 || { git diff; false; }
