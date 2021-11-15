# FPGA Interchange

This python module is designed to read and write FPGA interchange files, and
provide some interoperability with other common formats.

## Capabilities

This library supports the following capabilities:
 - Generate FPGA interchange files using Pythonic object model
 - Read FPGA interchange files into Pythonic object model
 - Sanity check logical netlist for completeness and correctness.
 - Sanity check a logical and physical netlist for completeness and
   correctness, given a device database.
 - Read some common logical netlist formats into the Pythonic object model:
   - (Planned) eblif
   - Yosys Netlist JSON
 - Basic (incomplete) placer constraint solver

## Basic placer constraint solver

The placer constraint solver enforces the constraints per 

### Running basic placer constraint solver

First generate xc7a35tcpg236-1 database from RapidWright:
```
"$RAPIDWRIGHT_PATH/scripts/invoke_rapidwright.sh" \
    com.xilinx.rapidwright.interchange.DeviceResourcesExample \
    xc7a50tfgg484-1
```

Annotated the xc7a35tcpg236-1 database with constraints:
```
python3 -mfpga_interchange.patch \
    --schema_dir $RAPIDWRIGHT_PATH/interchange \
    --schema device \
    --patch_path constraints \
    --patch_format yaml \
    xc7a35tcpg236-1.device \
    test_data/series7_constraints.yaml \
    xc7a35tcpg236-1_constraints.device
```

Write out example physical netlist:
```
python3 tests/example_netlist.py \
    --schema_dir "$RAPIDWRIGHT_PATH/interchange" \
    --logical_netlist simple.netlist \
    --physical_netlist simple.phys \
    --xdc simple.xdc
```

```
python3 -mfpga_interchange.constraints.tool \
    --schema_dir "$RAPIDWRIGHT_PATH/interchange" \
    --allowed_sites IOB_X0Y0,IOB_X0Y1,IOB_X0Y2,SLICE_X0Y0,BUFGCTRL_X0Y0 \
    --filtered_cells VCC,GND \
    --verbose \
    xc7a35tcpg236-1_constraints.device \
    simple.netlist
```

This repository was moved to CHIPS Alliance as of commit `b13ee55ebce` As part of the CHIPS due diligence process for non-Apache 2.0 projects, all contributors for over 1% of the codebase signed the CHIPS CLA: Antmicro (corporate CLA), Google (corporate CLA), gatecat (individual CLA). Any further contributions require a CLA to comply with the CHIPS Alliance IP policy.
