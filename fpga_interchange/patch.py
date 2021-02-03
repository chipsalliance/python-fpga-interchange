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
""" Small utility for patching FPGA interchange capnp files.

This utility completely replaces portion of the message at the specified
location.

"""
import argparse

from fpga_interchange.interchange_capnp import read_capnp_file, \
        write_capnp_file
from fpga_interchange.convert import SCHEMAS, FORMATS, get_schema, read_format_to_message
from fpga_interchange.json_support import to_json, from_json


def patch_capnp(message, patch_path, patch_format, in_f):
    message_to_populate = message
    for path in patch_path[:-1]:
        message_to_populate = getattr(message_to_populate, path)

    message_to_populate = message_to_populate.init(patch_path[-1])

    if patch_format == 'capnp':
        message = read_capnp_file(message_to_populate.schema, in_f)
        json_data = to_json(message)
        from_json(message_to_populate, json_data)
    else:
        read_format_to_message(message_to_populate, patch_format, in_f)


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument('--schema_dir', required=True)
    parser.add_argument('--schema', required=True, choices=SCHEMAS)
    parser.add_argument('--root_schema_path', default=None)
    parser.add_argument('--patch_path', required=True)
    parser.add_argument('--patch_format', required=True, choices=FORMATS)
    parser.add_argument('root')
    parser.add_argument('patch')
    parser.add_argument('output')

    args = parser.parse_args()

    patch_path = args.patch_path.split('.')

    root_schema = get_schema(args.schema_dir, args.schema,
                             args.root_schema_path)

    with open(args.root, 'rb') as f:
        message = read_capnp_file(root_schema, f)

    message = message.as_builder()

    with open(args.patch, 'rb') as f:
        patch_capnp(message, patch_path, args.patch_format, f)

    with open(args.output, 'wb') as f:
        write_capnp_file(message, f)


if __name__ == "__main__":
    main()
