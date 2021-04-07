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
from fpga_interchange.fasm_generators.generic import FasmGenerator
from fpga_interchange.route_stitching import flatten_segments
from fpga_interchange.physical_netlist import PhysicalPip


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

    def output_fasm(self):
        self.build_log_cells_instances()
        self.build_phys_cells_instances()

        site_thru_pips = self.fill_pip_features()
        self.handle_site_thru(site_thru_pips)
        self.handle_ios()

        for cell_feature in sorted(
                self.cells_features, key=lambda f: f.split(".")[0]):
            print(cell_feature)

        for routing_pip in sorted(
                self.routing_pips_features, key=lambda f: f.split(".")[0]):
            print(routing_pip)
