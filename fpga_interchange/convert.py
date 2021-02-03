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
""" Utilities for converting between file formats using string options.

This file provides a main function that allows conversions between supported
formats, and selecting subsets of the schemas where possible.

"""
import argparse
import json
import ryml
import yaml
from yaml import CSafeLoader as SafeLoader, CDumper as Dumper

from fpga_interchange.interchange_capnp import Interchange, read_capnp_file, write_capnp_file
from fpga_interchange.json_support import to_json, from_json
from fpga_interchange.rapidyaml_support import to_rapidyaml, from_rapidyaml
from fpga_interchange.yaml_support import to_yaml, from_yaml

SCHEMAS = ('device', 'logical', 'physical')
FORMATS = ('json', 'yaml', 'capnp', 'pyyaml')


def follow_path(schema_root, path):
    """ Follow path from schema_root to get a specific schema. """
    schema = schema_root

    for leaf in path:
        schema = getattr(schema, leaf)

    return schema


def read_format_to_message(message, input_format, in_f):
    if input_format == 'json':
        json_string = in_f.read().decode('utf-8')
        json_data = json.loads(json_string)
        from_json(message, json_data)
    elif input_format == 'yaml':
        yaml_string = in_f.read().decode('utf-8')
        yaml_tree = ryml.parse(yaml_string)
        from_rapidyaml(message, yaml_tree)
    elif input_format == 'pyyaml':
        yaml_string = in_f.read().decode('utf-8')
        yaml_data = yaml.load(yaml_string, Loader=SafeLoader)
        from_yaml(message, yaml_data)
    else:
        assert False, 'Invalid input format {}'.format(input_format)


def read_format(schema, input_format, in_f):
    """ Read serialized format into capnp message of specific schema.

    schema: Capnp schema for input format.
    input_format (str): Input format type, either capnp, json, yaml.
    in_f (file-like): Binary file that contains serialized data.

    Returns capnp message Builder of specified input format.

    """
    if input_format == 'capnp':
        message = read_capnp_file(schema, in_f)
        message = message.as_builder()
    elif input_format in ['json', 'yaml', 'pyyaml']:
        message = schema.new_message()
        read_format_to_message(message, input_format, in_f)
    else:
        assert False, 'Invalid input format {}'.format(input_format)

    return message


def write_format(message, output_format, out_f):
    """ Write capnp file to a serialized output format.

    message: Capnp Builder object to be serialized into output file.
    output_format (str): Input format type, either capnp, json, yaml.
    in_f (file-like): Binary file to writer to serialized format.

    """
    if output_format == 'capnp':
        write_capnp_file(message, out_f)
    elif output_format == 'json':
        message = message.as_reader()
        json_data = to_json(message)
        json_string = json.dumps(json_data, indent=2)
        out_f.write(json_string.encode('utf-8'))
    elif output_format == 'yaml':
        message = message.as_reader()
        strings, yaml_tree = to_rapidyaml(message)
        yaml_string = ryml.emit(yaml_tree)
        out_f.write(yaml_string.encode('utf-8'))
    elif output_format == 'pyyaml':
        message = message.as_reader()
        yaml_data = to_yaml(message)
        yaml_string = yaml.dump(yaml_data, sort_keys=False, Dumper=Dumper)
        out_f.write(yaml_string.encode('utf-8'))
    else:
        assert False, 'Invalid output format {}'.format(output_format)


def get_schema(schema_dir, schema, schema_path=None):
    """ Returns capnp schema based on directory of schemas, schema type.

    schema_dir (str): Path to directory containing schemas.
    schema (str): Schema type to return, either device, logical, physical.
    schema_path (str): Optional '.' seperated path to locate a schema.

    Returns capnp schema.

    """
    schemas = Interchange(schema_dir)

    schema_map = {
        'device': schemas.device_resources_schema,
        'logical': schemas.logical_netlist_schema,
        'physical': schemas.physical_netlist_schema,
    }

    # Make sure schema_map is complete.
    for schema_str in SCHEMAS:
        assert schema_str in schema_map

    if schema_path is None:
        default_path = {
            'device': ['Device'],
            'logical': ['Netlist'],
            'physical': ['PhysNetlist'],
        }
        path = default_path[schema]
    else:
        path = schema_path.split('.')

    schema = follow_path(schema_map[schema], path)

    return schema


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('--schema_dir', required=True)
    parser.add_argument('--schema', required=True, choices=SCHEMAS)
    parser.add_argument('--input_format', required=True, choices=FORMATS)
    parser.add_argument('--output_format', required=True, choices=FORMATS)
    parser.add_argument('--schema_path')
    parser.add_argument('input')
    parser.add_argument('output')

    args = parser.parse_args()

    schema = get_schema(args.schema_dir, args.schema, args.schema_path)

    with open(args.input, 'rb') as in_f:
        message = read_format(schema, args.input_format, in_f)

    with open(args.output, 'wb') as out_f:
        write_format(message, args.output_format, out_f)


if __name__ == "__main__":
    main()
