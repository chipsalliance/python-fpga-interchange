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
from collections import namedtuple

from fpga_interchange.route_stitching import flatten_segments
from fpga_interchange.physical_netlist import PhysicalPip

PhysCellInstance = namedtuple(
    'CellInstance', 'cell_type site_name tile_name sites_in_tile attributes')


class FasmGenerator():
    def __init__(self, interchange, device_resources, log_netlist_file,
                 phy_netlist_file):
        with open(device_resources, "rb") as f:
            self.device_resources = interchange.read_device_resources(f)

        with open(log_netlist_file, "rb") as f:
            self.logical_netlist = interchange.read_logical_netlist(f)

        with open(phy_netlist_file, "rb") as f:
            self.physical_netlist = interchange.read_physical_netlist(f)

        self.physical_cells_instances = dict()
        self.logical_cells_instances = dict()

        self.routing_pips_features = list()
        self.cells_features = list()

    def build_log_cells_instances(self):
        """
        Fills a dictionary with the logical cells with their attribute map
        """

        lib = self.logical_netlist.libraries["work"]
        for cell in lib.cells.values():
            for cell_instance, cell_obj in cell.cell_instances.items():

                cell_name = cell_obj.cell_name
                cell_attrs = cell_obj.property_map

                assert cell_instance not in self.logical_cells_instances, (
                    cell_instance, self.logical_cells_instances.keys())
                self.logical_cells_instances[cell_instance] = cell_attrs

    def build_phys_cells_instances(self):
        """
        Fills a dictionary for handy lookups of the placed sites and the corresponding tiles.

        The dictionary contains PhysCellInstance objects which are filled with the attribute
        map from the logical netlist
        """

        for placement in self.physical_netlist.placements:
            cell_name = placement.cell_name
            cell_type = placement.cell_type
            site_name = placement.site
            tile_name = self.device_resources.get_tile_name_at_site_name(
                site_name)
            tile = self.device_resources.tile_name_to_tile[tile_name]
            sites_in_tile = tile.site_names

            cell_attr = self.logical_cells_instances.get(cell_name, None)

            self.physical_cells_instances[cell_name] = PhysCellInstance(
                cell_type=cell_type,
                site_name=site_name,
                tile_name=tile_name,
                sites_in_tile=sites_in_tile,
                attributes=cell_attr)

    def fill_pip_features(self, site_thru_features=dict()):
        """
        This function generates all features corresponding to the physical routing
        PIPs present in the physical netlist.

        At the moment, the convention for the PIPs FASM features is:
            <TILE_NAME>.<WIRE1>.<WIRE0>

        where:
            TILE_NAME: is the name of the tile the PIP belongs to
            WIRE0: source PIP wire
            WIRE1: destination PIP wire

        Returns a list containing pseudo PIPs tuple, to be processed by the caller
        The list contains (<tile>, <wire0>, <wire1>) tuples.
        """

        site_thru_pips = list()

        for net in self.physical_netlist.nets:
            net_segments = flatten_segments(net.sources + net.stubs)

            for segment in net_segments:
                if isinstance(segment, PhysicalPip):
                    tile = segment.tile

                    tile_type_index = self.device_resources.tile_name_to_tile[
                        tile].tile_type_index
                    tile_type = self.device_resources.get_tile_type(
                        tile_type_index)

                    wire0 = segment.wire0
                    wire1 = segment.wire1

                    wire0_id = self.device_resources.string_index[wire0]
                    wire1_id = self.device_resources.string_index[wire1]

                    pip = tile_type.pip(wire0_id, wire1_id)
                    if pip.which() == "pseudoCells":
                        site_thru_pips.append((tile, wire0, wire1))
                        continue

                    self.routing_pips_features.append("{}.{}.{}".format(
                        tile, wire1, wire0))

        return site_thru_pips

    def output_fasm(self):
        """
        Function to generate and print out the FASM features.

        Needs to be implemented by the children classes.
        """
        pass
