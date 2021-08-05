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

from ..generic import FasmGenerator

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
            avail_lut_thrus, [],
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
                    2, site_type, "LUT4", bel, pin_name, "A")
            self.write_lut(tile_name, bel, lut_init)

    def get_logic_tiletypes(self):
        """
        This function gets a list of tiletypes that can contain logic
        """
        logic_tiletypes = set()
        for _, _, tile_type, _, _, bel_type in self.device_resources.yield_bels(
        ):
            if bel_type == "OXIDE_COMB":
                logic_tiletypes.add(tile_type)
        return logic_tiletypes

    def handle_slice_routing_bels(self):
        tile_types = self.get_logic_tiletypes()
        routing_bels = self.get_routing_bels(tile_types)

        for site, bel, pin, _ in routing_bels:
            tile = site.replace("_PLC", "__PLC")
            dst_wire = bel.replace("RBEL_", "")
            feature = "{}.{}".format(dst_wire, pin)
            self.add_cell_feature((tile, "PIP", feature))

    def handle_slice_ff(self):
        for cell_instance, cell_data in self.physical_cells_instances.items():
            if not cell_data.cell_type.startswith("FD1P3"):
                continue
            bel_tile = "{}__PLC".format(cell_data.tile_name)
            bel_prefix = cell_data.bel.replace("_FF", ".REG")

            self.add_cell_feature((bel_tile, bel_prefix, "USED.YES"))
            regset = "SET" if cell_data.cell_type in ("FD1P3BX",
                                                      "FD1P3JX") else "RESET"
            self.add_cell_feature((bel_tile, bel_prefix,
                                   "REGSET.{}".format(regset)))
            self.add_cell_feature((bel_tile, bel_prefix, "LSRMODE.LSR"))
            self.add_cell_feature((bel_tile, bel_prefix,
                                   "SEL.DF"))  # TODO: LUT->FF path

            slice_prefix = cell_data.bel.split("_")[0]
            srmode = "ASYNC" if cell_data.cell_type in (
                "FD1P3BX", "FD1P3DX") else "LSR_OVER_CE"
            self.add_cell_feature((bel_tile, slice_prefix,
                                   "SRMODE.{}".format(srmode)))
            # TODO: control set inversion/constants
            self.add_cell_feature((bel_tile, slice_prefix, "CLKMUX.CLK"))
            self.add_cell_feature((bel_tile, slice_prefix, "LSRMUX.LSR"))
            self.add_cell_feature((bel_tile, slice_prefix, "CEMUX.CE"))

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

    def handle_brams(self):
        """
        This function handles BRAMs FASM features generation
        """

        # WID (write IDs) are used to match init data to BRAM instances
        curr_wid = 2

        for cell_instance, cell_data in self.physical_cells_instances.items():
            if cell_data.cell_type not in ("PDPSC16K_MODE", "PDP16K_MODE",
                                           "DP16K_MODE"):
                continue
            # Not yet supported
            assert cell_data.cell_type != "DP16K_MODE", cell_instance
            site = cell_data.site_name
            bel = cell_data.bel
            mode = cell_data.cell_type
            self.add_cell_feature((site, bel, "MODE.{}".format(mode)))
            for param in ("ASYNC_RST_RELEASE", "DATA_WIDTH_W", "DATA_WIDTH_R",
                          "OUTREG", "RESETMODE"):
                if param not in cell_data.attributes:
                    continue
                self.add_cell_feature((site, bel, "{}.{}.{}".format(
                    mode, param, cell_data.attributes[param])))
            self.add_cell_feature((site, bel,
                                   "{}.CSDECODE_R[2:0] = 3'b000".format(mode)))
            self.add_cell_feature((site, bel,
                                   "{}.CSDECODE_W[2:0] = 3'b000".format(mode)))
            self.add_cell_feature((site, bel, "DP16K_MODE.CLKAMUX.CLKA"))
            self.add_cell_feature((site, bel, "DP16K_MODE.CLKBMUX.CLKB"))
            self.add_cell_feature((site, bel, "INIT_DATA.STATIC"))
            self.add_cell_feature((site, bel,
                                   "WID[10:0] = 11'b{:011b}".format(curr_wid)))
            for i in range(0x40):
                param = "INITVAL_{:02X}".format(i)
                if param not in cell_data.attributes:
                    continue
                self.add_cell_feature(
                    ("IP_EBR_WID{}".format(curr_wid), "{}[319:0] = {}".format(
                        param, cell_data.attributes[param].replace(
                            "0x", "320'h"))))
            curr_wid += 1

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

    def handle_osc(self):
        for cell_instance, cell_data in self.physical_cells_instances.items():
            if cell_data.cell_type != "OSC_CORE":
                continue
            site = cell_data.site_name
            bel = cell_data.bel
            self.add_cell_feature((site, bel, "HF_OSC_EN.ENABLED"))
            self.add_cell_feature((site, bel, "HFDIV_FABRIC_EN.ENABLED"))
            self.add_cell_feature((site, bel, "DEBUG_N.DISABLED"))
            self.add_cell_feature(
                (site, bel, "HF_CLK_DIV[7:0] = 8'b{:08b}".format(
                    int(cell_data.attributes.get("HF_CLK_DIV", "1")))))

    def fill_features(self):
        dev_name = self.device_resources.device_resource_capnp.name
        self.add_annotation("oxide.device", dev_name)
        self.add_annotation("oxide.device_variant", "ES")
        self.handle_luts()
        self.handle_brams()
        self.handle_io()
        self.handle_osc()
        # Handling PIPs and Route-throughs
        self.handle_pips()
        self.handle_slice_ff()
        self.handle_slice_routing_bels()
