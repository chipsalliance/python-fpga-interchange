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
import argparse

from fpga_interchange.interchange_capnp import Interchange
from fpga_interchange.fasm_generators.xc7 import XC7FasmGenerator


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        '--schema_dir',
        required=True,
        help="Path to the FPGA interchange schemas directory.")
    parser.add_argument(
        '--family', required=True, help="Device family. E.g. xc7, xcu, etc.")
    parser.add_argument('device_resources', help="Device resources file.")
    parser.add_argument('logical_netlist', help="Logical netlist file.")
    parser.add_argument('physical_netlist', help="Physical netlist file.")
    parser.add_argument('fasm_file', help="FASM output file.")

    args = parser.parse_args()

    interchange = Interchange(args.schema_dir)

    family_map = {
        "xc7": XC7FasmGenerator,
    }

    device_resources = args.device_resources
    logical_net = args.logical_netlist
    physical_net = args.physical_netlist
    fasm_file = args.fasm_file

    fasm_generator = family_map[args.family](interchange, device_resources,
                                             logical_net, physical_net)
    fasm_generator.fill_features()
    fasm_generator.output_fasm(fasm_file)


if __name__ == "__main__":
    main()
