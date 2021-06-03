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

VCC_NET = "GLOBAL_LOGIC1"
GND_NET = "GLOBAL_LOGIC0"


class NexusFasmGenerator(FasmGenerator):
    def handle_pips(self):
        pip_feature_format = "{tile}.PIP.{wire1}.{wire0}"
        avail_lut_thrus = list()
        for _, _, _, _, bel, bel_type in self.device_resources.yield_bels():
            if bel_type == "OXIDE_COMB":
                avail_lut_thrus.append(bel)

        site_thru_pips, lut_thru_pips = self.fill_pip_features(
            pip_feature_format, {},
            avail_lut_thrus,
            wire_rename=lambda x: x.replace(":", "__"))
        self.handle_lut_thru(lut_thru_pips)

    def write_lut(self, tile, bel, init):
        bel_tile = "{}__PLC".format(tile)
        bel_prefix = bel.replace("_LUT", ".K")
        self.add_cell_feature((bel_tile, bel_prefix,
                               "INIT[15:0] = 16'b{}".format(init)))

    def handle_lut_thru(self, lut_thru_pips):
        for (net_name, site, bel), pin in lut_thru_pips.items():
            pin_name = pin["pin_name"]
            is_valid = pin["is_valid"]
            if not is_valid:
                continue
            tile_name, _ = self.get_tile_info_at_site(site)
            site_type = list(
                self.device_resources.site_name_to_site[site].keys())[0]

            if net_name == VCC_NET:
                lut_init = self.lut_mapper.get_const_lut_init(
                    1, site_type, bel)
            elif net_name == GND_NET:
                lut_init = self.lut_mapper.get_const_lut_init(
                    0, site_type, bel)
            else:
                lut_init = self.lut_mapper.get_phys_wire_lut_init(
                    2, site_type, "LUT1", bel, pin_name)
            self.write_lut(tile_name, bel, lut_init)

    def handle_luts(self):
        """
        This function handles LUTs FASM features generation
        """
        for cell_instance, cell_data in self.physical_cells_instances.items():
            if cell_data.cell_type != "LUT4":
                continue

            init_param = self.device_resources.get_parameter_definition(
                cell_data.cell_type, "INIT")
            init_value = init_param.decode_integer(
                cell_data.attributes["INIT"])

            phys_lut_init = self.lut_mapper.get_phys_cell_lut_init(
                init_value, cell_data)
            self.write_lut(cell_data.tile_name, cell_data.bel, phys_lut_init)

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
        self.handle_luts()
        self.handle_io()
        # Handling PIPs and Route-throughs
        self.handle_pips()
