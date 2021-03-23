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
import os

from fpga_interchange.interchange_capnp import Interchange
from fpga_interchange.converters import Enumerator
from fpga_interchange.nextpnr import BbaWriter
from fpga_interchange.populate_chip_info import populate_chip_info
import yaml


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--schema_dir', required=True)
    parser.add_argument('--output_dir', required=True)
    parser.add_argument('--device', required=True)
    parser.add_argument('--device_config', required=True)

    args = parser.parse_args()
    interchange = Interchange(args.schema_dir)

    with open(args.device, 'rb') as f:
        device = interchange.read_device_resources(f)

    with open(args.device_config, 'r') as f:
        device_config = yaml.safe_load(f.read())

    const_ids = Enumerator()

    # ID = 0 is always the empty string!
    assert const_ids.get_index('') == 0

    if 'global_buffers' in device_config:
        global_buffers = device_config['global_buffers']
    else:
        global_buffers = []

    chip_info = populate_chip_info(device, const_ids, global_buffers,
                                   device_config['buckets'])

    with open(os.path.join(args.output_dir, 'chipdb.bba'), 'w') as f:
        bba = BbaWriter(f, const_ids)
        bba.pre("#include \"nextpnr.h\"")
        bba.pre("NEXTPNR_NAMESPACE_BEGIN")
        bba.post("NEXTPNR_NAMESPACE_END")
        bba.push("chipdb_blob")

        root_prefix = 'chip_info'
        bba.ref(root_prefix, root_prefix)
        chip_info.append_bba(bba, root_prefix)

        bba.label(chip_info.strings_label(root_prefix), 'strings_slice')
        bba.ref('strings_data')
        bba.u32(len(const_ids.values) - 1)

        bba.label('strings_data', 'strings')
        for s in const_ids.values[1:]:
            bba.str(s)

        bba.pop()

    bba.check_labels()

    with open(os.path.join(args.output_dir, 'constids.txt'), 'w') as f:
        for s in const_ids.values[1:]:
            print('X({})'.format(s), file=f)


if __name__ == "__main__":
    main()
