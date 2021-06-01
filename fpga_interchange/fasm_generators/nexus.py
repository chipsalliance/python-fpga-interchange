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
"""
This file defines the Nexus devices FASM generator class.
"""
import re
from collections import namedtuple
from enum import Enum
from itertools import product

from fpga_interchange.fasm_generators.generic import FasmGenerator


class NexusFasmGenerator(FasmGenerator):
    def handle_pips(self):
        pip_feature_format = "{tile}.PIP.{wire1}.{wire0}"
        site_thru_pips, lut_thru_pips = self.fill_pip_features(
            pip_feature_format, {}, {},
            wire_rename=lambda x: x.replace(":", "__"))

    def handle_io(self):
        allowed_io_types = {
            "OB": [
                "BASE_TYPE.OUTPUT_LVCMOS33",
                "TMUX.INV",
            ],
            "IB": [
                "BASE_TYPE.INPUT_LVCMOS33",
            ]
        }
        for cell_instance, cell_data in self.physical_cells_instances.items():
            if cell_data.cell_type not in allowed_io_types:
                continue
            for feature in allowed_io_types[cell_data.cell_type]:
                self.add_cell_feature((cell_data.site_name, cell_data.bel,
                                       feature))

    def fill_features(self):
        dev_name = self.device_resources.device_resource_capnp.name
        self.add_annotation("oxide.device", dev_name)
        self.add_annotation("oxide.device_variant", "ES")
        self.handle_io()
        # Handling PIPs and Route-throughs
        self.handle_pips()
