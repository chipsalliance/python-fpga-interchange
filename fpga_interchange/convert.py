#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2020  The SymbiFlow Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
import argparse
import json
import ryml

from fpga_interchange.interchange_capnp import Interchange, read_capnp_file, write_capnp_file
from fpga_interchange.json_support import to_json, from_json
from fpga_interchange.rapidyaml_support import to_rapidyaml, from_rapidyaml

SCHEMAS = ('device', 'logical', 'physical')
FORMATS = ('json', 'yaml', 'capnp')


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('--schema_dir', required=True)
    parser.add_argument('--schema', required=True, choices=SCHEMAS)
    parser.add_argument('--input_format', required=True, choices=FORMATS)
    parser.add_argument('--output_format', required=True, choices=FORMATS)
    parser.add_argument('input')
    parser.add_argument('output')

    args = parser.parse_args()

    schemas = Interchange(args.schema_dir)

    schema_map = {
        'device': schemas.device_resources_schema.Device,
        'logical': schemas.logical_netlist_schema.Netlist,
        'physical': schemas.physical_netlist_schema.PhysNetlist,
    }

    for schema_str in SCHEMAS:
        assert schema_str in schema_map

    schema = schema_map[args.schema]

    if args.input_format == 'capnp':
        with open(args.input, 'rb') as f:
            message = read_capnp_file(schema, f)
            message = message.as_builder()
    elif args.input_format == 'json':
        with open(args.input, 'r') as f:
            json_data = json.load(f)

        message = schema.new_message()
        from_json(message, json_data)
    elif args.input_format == 'yaml':
        with open(args.input, 'r') as f:
            yaml_string = f.read()

        yaml_tree = ryml.parse(yaml_string)
        message = schema.new_message()
        from_rapidyaml(message, yaml_tree)
    else:
        assert False, 'Invalid input format {}'.format(args.input_format)

    if args.output_format == 'capnp':
        with open(args.output, 'wb') as f:
            write_capnp_file(message, f)
    elif args.output_format == 'json':
        message = message.as_reader()
        json_data = to_json(message)
        with open(args.output, 'w') as f:
            json.dump(json_data, f)
    elif args.output_format == 'yaml':
        message = message.as_reader()
        strings, yaml_tree = to_rapidyaml(message)
        yaml_string = ryml.emit(yaml_tree)
        with open(args.output, 'w') as f:
            f.write(yaml_string)
    else:
        assert False, 'Invalid output format {}'.format(args.output_format)


if __name__ == "__main__":
    main()
