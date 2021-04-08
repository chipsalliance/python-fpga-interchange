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
import re
from enum import Enum

from fpga_interchange.fasm_generators.generic import FasmGenerator
from fpga_interchange.route_stitching import flatten_segments
from fpga_interchange.physical_netlist import PhysicalPip


class LutsEnum(Enum):
    LUT5 = 0
    LUT6 = 1

    @classmethod
    def from_str(cls, label):
        if label == "LUT5":
            return cls.LUT5
        elif label == "LUT6":
            return cls.LUT6
        else:
            raise NotImplementedError


class XC7FasmGenerator(FasmGenerator):
    def handle_ios(self):
        """
        This function is specialized to add FASM features for the IO buffers
        in the 7-Series database format.
        """

        # FIXME: Need to make this dynamic, and find a suitable way to add FASM annotations to the device resources.
        #        In addition, a reformat of the database might be required to have an easier handling of these
        #        features.
        allowed_io_types = {
            "OBUF": [
                "LVCMOS12_LVCMOS15_LVCMOS18_LVCMOS25_LVCMOS33_LVTTL_SSTL135_SSTL15.SLEW.SLOW",
                "LVCMOS33_LVTTL.DRIVE.I12_I16", "PULLTYPE.NONE"
            ],
            "IBUF": [
                "LVCMOS12_LVCMOS15_LVCMOS18_LVCMOS25_LVCMOS33_LVTTL.SLEW.FAST",
                "LVCMOS12_LVCMOS15_LVCMOS18_LVCMOS25_LVCMOS33_LVDS_25_LVTTL_SSTL135_SSTL15_TMDS_33.IN_ONLY",
                "LVCMOS25_LVCMOS33_LVTTL.IN", "PULLTYPE.NONE"
            ]
        }

        iob_sites = ["IOB_Y1", "IOB_Y0"]

        for cell_instance, cell_data in self.physical_cells_instances.items():
            if cell_data.cell_type not in allowed_io_types:
                continue

            iob_site_idx = cell_data.sites_in_tile.index(cell_data.site_name)

            iob_site = iob_sites[
                iob_site_idx] if "SING" not in cell_data.tile_name else "IOB_Y0"

            for feature in allowed_io_types[cell_data.cell_type]:
                self.cells_features.append("{}.{}.{}".format(
                    cell_data.tile_name, iob_site, feature))

    @staticmethod
    def get_slice_prefix(site_name, tile_type, sites_in_tile):
        """
        Returns the slice prefix corresponding to the input site name.
        """

        slice_sites = {
            "CLBLL_L": ["SLICEL_X1", "SLICEL_X0"],
            "CLBLL_R": ["SLICEL_X1", "SLICEL_X0"],
            "CLBLM_L": ["SLICEL_X1", "SLICEM_X0"],
            "CLBLM_R": ["SLICEL_X1", "SLICEM_X0"],
        }

        slice_site_idx = sites_in_tile.index(site_name)
        return slice_sites[tile_type][slice_site_idx]

    def handle_luts(self):
        """
        This function handles LUTs FASM features generation
        """

        bel_re = re.compile("([ABCD])([56])LUT")

        luts = dict()

        for cell_instance, cell_data in self.physical_cells_instances.items():
            if not cell_data.cell_type.startswith("LUT"):
                continue

            site_name = cell_data.site_name
            site_type = cell_data.site_type

            tile_name = cell_data.tile_name
            tile_type = cell_data.tile_type
            sites_in_tile = cell_data.sites_in_tile
            slice_site = self.get_slice_prefix(site_name, tile_type,
                                               sites_in_tile)

            bel = cell_data.bel
            m = bel_re.match(bel)
            assert m, bel

            # A, B, C or D
            lut_loc = m.group(1)
            lut_name = "{}LUT".format(lut_loc)

            # LUT5 or LUT6
            lut_type = "LUT{}".format(m.group(2))

            init_param = self.device_resources.get_parameter_definition(
                cell_data.cell_type, "INIT")
            init_value = init_param.decode_integer(
                cell_data.attributes["INIT"])

            phys_lut_init = self.get_phys_lut_init(init_value, cell_data)

            key = (site_name, lut_loc)
            if key not in luts:
                luts[key] = {
                    "data": (tile_name, slice_site, lut_name),
                    LutsEnum.LUT5: None,
                    LutsEnum.LUT6: None,
                }

            luts[key][LutsEnum.from_str(lut_type)] = phys_lut_init

        for lut in luts.values():
            tile_name, slice_site, lut_name = lut["data"]

            lut5 = lut[LutsEnum.LUT5]
            lut6 = lut[LutsEnum.LUT6]

            if lut5 is not None and lut6 is not None:
                lut_init = "{}{}".format(lut6[0:32], lut5[32:64])
            elif lut5 is not None:
                lut_init = lut5
            elif lut6 is not None:
                lut_init = lut6
            else:
                assert False

            init_feature = "{}.INIT[{}:0]={}'b{}".format(
                lut_name,
                len(lut_init) - 1, len(lut_init), lut_init)
            lut_feature = "{}.{}.{}".format(tile_name, slice_site,
                                            init_feature)

            self.cells_features.append(lut_feature)

    def handle_site_thru(self, site_thru_pips):
        """
        This function is currently specialized to add very specific features
        for pseudo PIPs which need to be enabled to get the correct HW behaviour
        """

        # FIXME: this information needs to be added as an annotation
        #        to the device resources
        wire_to_features_map = {
            "IOI_OLOGIC0_D1": [
                "OLOGIC_Y0.OMUX.D1", "OLOGIC_Y0.OQUSED",
                "OLOGIC_Y0.OSERDES.DATA_RATE_TQ.BUF"
            ],
            "IOI_OLOGIC1_D1": [
                "OLOGIC_Y1.OMUX.D1", "OLOGIC_Y1.OQUSED",
                "OLOGIC_Y1.OSERDES.DATA_RATE_TQ.BUF"
            ]
        }

        for tile, wire0, wire1 in site_thru_pips:
            features = wire_to_features_map.get(wire0, [])

            for feature in features:
                self.cells_features.append("{}.{}".format(tile, feature))

    def handle_slice_routing_bels(self):
        allowed_routing_bels = list()

        for loc in "ABCD":
            ff_mux = "{}FFMUX".format(loc)
            out_mux = "{}OUTMUX".format(loc)
            allowed_routing_bels.extend([ff_mux, out_mux])

        routing_bels = self.get_routing_bels(allowed_routing_bels)

        for site, bel, pin in routing_bels:
            tile_name, tile_type, sites_in_tile = self.get_tile_info_at_site(
                site)
            slice_prefix = self.get_slice_prefix(site, tile_type,
                                                 sites_in_tile)

            routing_bel_feature = "{}.{}.{}.{}".format(tile_name, slice_prefix,
                                                       bel, pin)
            self.cells_features.append(routing_bel_feature)

    def output_fasm(self):
        site_thru_pips = self.fill_pip_features()
        self.handle_site_thru(site_thru_pips)
        self.handle_slice_routing_bels()
        self.handle_ios()
        self.handle_luts()

        for cell_feature in sorted(
                self.cells_features, key=lambda f: f.split(".")[0]):
            print(cell_feature)

        for routing_pip in sorted(
                self.routing_pips_features, key=lambda f: f.split(".")[0]):
            print(routing_pip)
