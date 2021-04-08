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
from math import log2

from fpga_interchange.route_stitching import flatten_segments
from fpga_interchange.physical_netlist import PhysicalPip, PhysicalSitePip
from fpga_interchange.chip_info_utils import LutCell, LutBel, LutElement

PhysCellInstance = namedtuple(
    'CellInstance',
    'cell_type site_name site_type tile_name tile_type sites_in_tile bel bel_pins attributes'
)


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
        self.build_luts_definitions()
        self.build_log_cells_instances()
        self.build_phys_cells_instances()
        self.flatten_nets()

    def flatten_nets(self):
        self.flattened_nets = dict()

        for net in self.physical_netlist.nets:
            self.flattened_nets[net.name] = flatten_segments(net.sources +
                                                             net.stubs)

    def get_tile_info_at_site(self, site_name):
        tile_name = self.device_resources.get_tile_name_at_site_name(site_name)
        tile = self.device_resources.tile_name_to_tile[tile_name]
        tile_type = tile.tile_type
        sites_in_tile = tile.site_names

        return tile_name, tile_type, sites_in_tile

    def build_luts_definitions(self):
        """
        Fills luts definition from the device resources database
        """

        self.site_lut_elements = dict()
        self.lut_cells = dict()

        for site_lut_element in self.device_resources.device_resource_capnp.lutDefinitions.lutElements:
            site = site_lut_element.site
            self.site_lut_elements[site] = list()
            for lut in site_lut_element.luts:
                lut_element = LutElement()
                self.site_lut_elements[site].append(lut_element)

                lut_element.width = lut.width

                for bel in lut.bels:
                    lut_bel = LutBel()
                    lut_element.lut_bels.append(lut_bel)

                    lut_bel.name = bel.name
                    for pin in bel.inputPins:
                        lut_bel.pins.append(pin)

                    lut_bel.out_pin = bel.outputPin

                    assert bel.lowBit < lut.width
                    assert bel.highBit < lut.width

                    lut_bel.low_bit = bel.lowBit
                    lut_bel.high_bit = bel.highBit

        for lut_cell in self.device_resources.device_resource_capnp.lutDefinitions.lutCells:
            lut = LutCell()
            self.lut_cells[lut_cell.cell] = lut

            lut.name = lut_cell.cell
            for pin in lut_cell.inputPins:
                lut.pins.append(pin)

    def get_phys_lut_init(self, logical_init_value, cell_data):
        """
        Returns the LUTs physical INIT parameter mapping given the initial logical INIT
        value and the cells' data containing the physical mapping of the input pins.

        It is left to the caller to handle cases of fructured LUTs.
        """

        def find_lut_bel(lut_elements, bel):
            """ Returns the LUT Bel definition and the corresponding LUT element. """
            for lut_element in lut_elements:
                for lut_bel in lut_element.lut_bels:
                    if lut_bel.name == bel:
                        return lut_element, lut_bel

        def physical_to_logical_map(lut_bel, bel_pins):
            """
            Returns the physical pin to logical pin LUTs mapping.
            Unused physical pins are set to None.
            """
            phys_to_log = dict()

            for pin in lut_bel.pins:
                phys_to_log[pin] = None

                for bel_pin in bel_pins:
                    if bel_pin.bel_pin == pin:
                        phys_to_log[pin] = bel_pin.cell_pin
                        break

            return phys_to_log

        cell_type = cell_data.cell_type
        bel = cell_data.bel
        bel_pins = cell_data.bel_pins
        site_type = cell_data.site_type

        assert site_type in self.site_lut_elements, site_type
        lut_elements = self.site_lut_elements[site_type]

        lut_element, lut_bel = find_lut_bel(lut_elements, bel)
        lut_cell = self.lut_cells[cell_type]

        bitstring_init = "{value:0{digits}b}".format(
            value=logical_init_value, digits=lut_bel.high_bit + 1)

        # Invert the string to have the LSB in the beginning
        logical_lut_init = bitstring_init[::-1]
        phys_to_log = physical_to_logical_map(lut_bel, bel_pins)

        physical_lut_init = list()
        for phys_init_index in range(0, lut_element.width):
            log_init_index = 0

            for phys_port_idx in range(0, int(log2(lut_element.width))):
                if not phys_init_index & (1 << phys_port_idx):
                    continue

                if phys_port_idx < len(lut_bel.pins):
                    log_port = phys_to_log.get(lut_bel.pins[phys_port_idx])

                if log_port is None:
                    continue

                log_port_idx = lut_cell.pins.index(log_port)
                log_init_index |= (1 << log_port_idx)

            physical_lut_init.append(logical_lut_init[log_init_index])

        # Generate a string and invert the list, to have MSB in first position
        return "".join(physical_lut_init[::-1])

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
            site_type = self.physical_netlist.site_instances[site_name]

            tile_name, tile_type, sites_in_tile = self.get_tile_info_at_site(
                site_name)

            bel = placement.bel
            bel_pins = placement.pins
            cell_attr = self.logical_cells_instances.get(cell_name, None)

            self.physical_cells_instances[cell_name] = PhysCellInstance(
                cell_type=cell_type,
                site_name=site_name,
                site_type=site_type,
                tile_name=tile_name,
                tile_type=tile_type,
                sites_in_tile=sites_in_tile,
                bel=bel,
                bel_pins=bel_pins,
                attributes=cell_attr)

    def fill_pip_features(self):
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
            for segment in self.flattened_nets[net.name]:
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

    def get_routing_bels(self, allowed_routing_bels):

        routing_bels = list()

        for net in self.physical_netlist.nets:
            for segment in self.flattened_nets[net.name]:
                if isinstance(segment, PhysicalSitePip):
                    bel = segment.bel
                    if bel not in allowed_routing_bels:
                        continue

                    site = segment.site
                    pin = segment.pin

                    routing_bels.append((site, bel, pin))

        return routing_bels

    def output_fasm(self):
        """
        Function to generate and print out the FASM features.

        Needs to be implemented by the children classes.
        """
        pass
