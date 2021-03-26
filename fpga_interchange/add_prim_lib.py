#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2021  The SymbiFlow Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
""" Utility for adding a primitive library to a device from Yosys JSON

This takes a Yosys JSON of blackboxes (e.g. that produced by "synth_arch; write_json"
without any design) and patches a device capnp to include those boxes as primLibs.

Example usage:

yosys -p "synth_nexus; write_json nexus_boxes.json"
python -mfpga_interchange.add_prim_lib --schema_dir ${SCHEMA_DIR} \
    nexus_unpatched.device nexus_boxes.json nexus_patched.device

"""
import argparse
import json
import re

from fpga_interchange.interchange_capnp import Interchange, read_capnp_file, write_capnp_file
from fpga_interchange.logical_netlist import LogicalNetlist, Cell, \
        CellInstance, Direction, Library

from fpga_interchange.yosys_json import is_bus


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--schema_dir', required=True)
    parser.add_argument('--library', default="primitives")
    parser.add_argument('device_in')
    parser.add_argument('yosys_json')
    parser.add_argument('device_out')

    args = parser.parse_args()
    interchange = Interchange(args.schema_dir)
    with open(args.device_in, 'rb') as f:
        device = read_capnp_file(interchange.device_resources_schema.Device, f)

    device = device.as_builder()

    with open(args.yosys_json) as f:
        yosys_json = json.load(f)

    prim_lib = Library(args.library)

    assert 'modules' in yosys_json, yosys_json.keys()
    for module_name, module_data in sorted(
            yosys_json['modules'].items(), key=lambda x: x[0]):
        # Library should only contain blackboxes
        assert module_data['attributes'].get('blackbox', 0) or \
            module_data['attributes'].get('whitebox', 0), module_name
        property_map = {}
        if 'attributes' in module_data:
            property_map.update(module_data['attributes'])
        if 'parameters' in module_data:
            property_map.update(module_data['parameters'])
        cell = Cell(module_name, property_map)

        for port_name, port_data in module_data['ports'].items():
            if port_data['direction'] == 'input':
                direction = Direction.Input
            elif port_data['direction'] == 'output':
                direction = Direction.Output
            else:
                assert port_data['direction'] == 'inout'
                direction = Direction.Inout

            property_map = {}
            if 'attributes' in port_data:
                property_map = port_data['attributes']

            offset = port_data.get('offset', 0)
            upto = port_data.get('upto', False)

            if is_bus(port_data['bits'], offset, upto):
                end = offset
                start = offset + len(port_data['bits']) - 1

                if upto:
                    start, end = end, start

                cell.add_bus_port(
                    name=port_name,
                    direction=direction,
                    start=start,
                    end=end,
                    property_map=property_map)
            else:
                cell.add_port(
                    name=port_name,
                    direction=direction,
                    property_map=property_map)
        prim_lib.add_cell(cell)

    libraries = {}
    libraries[args.library] = prim_lib
    # Create the netlist
    netlist = LogicalNetlist(
        name=args.library,
        property_map={},
        top_instance_name=None,
        top_instance=None,
        libraries=libraries)

    netlist_capnp = netlist.convert_to_capnp(interchange)

    # Patch device
    device.primLibs = netlist_capnp

    # Save patched device
    with open(args.device_out, 'wb') as f:
        write_capnp_file(device, f)


if __name__ == "__main__":
    main()
