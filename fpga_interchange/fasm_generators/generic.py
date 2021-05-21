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

from fpga_interchange import get_version
from fpga_interchange.route_stitching import flatten_segments
from fpga_interchange.physical_netlist import PhysicalPip, PhysicalSitePip, PhysicalBelPin
from fpga_interchange.logical_netlist import Direction
from fpga_interchange.chip_info_utils import LutCell, LutBel, LutElement

PhysCellInstance = namedtuple(
    'CellInstance',
    'cell_type site_name site_type tile_name tile_type bel bel_pins attributes'
)


def invert_bitstring(string):
    """ This function inverts all bits in a bitstring. """
    return string.replace("1", "2").replace("0", "1").replace("2", "0")


class LutMapper():
    def __init__(self, device_resources):
        """
        Fills luts definition from the device resources database
        """

        self.site_lut_elements = dict()
        self.lut_cells = dict()

        for site_lut_element in device_resources.device_resource_capnp.lutDefinitions.lutElements:
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

        for lut_cell in device_resources.device_resource_capnp.lutDefinitions.lutCells:
            lut = LutCell()
            self.lut_cells[lut_cell.cell] = lut

            lut.name = lut_cell.cell
            for pin in lut_cell.inputPins:
                lut.pins.append(pin)

    def find_lut_bel(self, site_type, bel):
        """
        Returns the LUT Bel definition and the corresponding LUT element given the
        corresponding site_type and bel name
        """
        assert site_type in self.site_lut_elements, site_type
        lut_elements = self.site_lut_elements[site_type]

        for lut_element in lut_elements:
            for lut_bel in lut_element.lut_bels:
                if lut_bel.name == bel:
                    return lut_element, lut_bel

        assert False

    def get_phys_lut_init(self, log_init, lut_element, lut_bel, lut_cell,
                          phys_to_log):
        bitstring_init = "{value:0{digits}b}".format(
            value=log_init, digits=lut_bel.high_bit + 1)

        # Invert the string to have the LSB at the beginning
        logical_lut_init = bitstring_init[::-1]

        physical_lut_init = str()
        for phys_init_index in range(0, lut_element.width):
            log_init_index = 0

            for phys_port_idx in range(0, int(log2(lut_element.width))):
                if not phys_init_index & (1 << phys_port_idx):
                    continue

                log_port = None
                if phys_port_idx < len(lut_bel.pins):
                    log_port = phys_to_log.get(lut_bel.pins[phys_port_idx])

                if log_port is None:
                    continue

                log_port_idx = lut_cell.pins.index(log_port)
                log_init_index |= (1 << log_port_idx)

            physical_lut_init += logical_lut_init[log_init_index]

        # Invert the string to have the MSB at the beginning
        return physical_lut_init[::-1]

    def get_phys_cell_lut_init(self, logical_init_value, cell_data):
        """
        Returns the LUTs physical INIT parameter mapping given the initial logical INIT
        value and the cells' data containing the physical mapping of the input pins.

        It is left to the caller to handle cases of fractured LUTs.
        """

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

        lut_element, lut_bel = self.find_lut_bel(site_type, bel)
        phys_to_log = physical_to_logical_map(lut_bel, bel_pins)
        lut_cell = self.lut_cells[cell_type]

        return self.get_phys_lut_init(logical_init_value, lut_element, lut_bel,
                                      lut_cell, phys_to_log)

    def get_phys_wire_lut_init(self, logical_init_value, site_type, cell_type,
                               bel, bel_pin):
        """
        Returns the LUTs physical INIT parameter mapping of a LUT-thru wire

        It is left to the caller to handle cases of fructured LUTs.
        """

        lut_element, lut_bel = self.find_lut_bel(site_type, bel)
        lut_cell = self.lut_cells[cell_type]
        assert len(lut_cell.pins) == 1, (lut_cell.name, lut_cell.pins)
        phys_to_log = dict((pin, None) for pin in lut_bel.pins)
        phys_to_log[bel_pin] = lut_cell.pins[0]

        return self.get_phys_lut_init(logical_init_value, lut_element, lut_bel,
                                      lut_cell, phys_to_log)

    def get_const_lut_init(self, const_init_value, site_type, bel):
        """
        Returns the LUTs physical INIT parameter mapping of a wire tied to
        the constant net (GND or VCC).
        """

        lut_element, _ = self.find_lut_bel(site_type, bel)
        width = lut_element.width

        return "".rjust(width, str(const_init_value))


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

        self.build_log_cells_instances()
        self.build_phys_cells_instances()
        self.flatten_nets()

        self.routing_bels = dict()

        self.pips_features = set()
        self.cells_features = set()

        self.lut_mapper = LutMapper(self.device_resources)

    def get_origin_line(self):
        version = get_version()

        return "# Created by the FPGA Interchange FASM Generator (v{})".format(
            version)

    def add_cell_feature(self, feature_parts):
        feature_str = ".".join(feature_parts)
        self.cells_features.add(feature_str)

    def add_pip_feature(self, feature_parts, pip_feature_format):
        tile, wire0, wire1 = feature_parts
        feature_str = pip_feature_format.format(
            tile=tile, wire0=wire0, wire1=wire1)
        self.pips_features.add(feature_str)

    def flatten_nets(self):
        self.flattened_nets = dict()

        for net in self.physical_netlist.nets:
            self.flattened_nets[net.name] = flatten_segments(net.sources +
                                                             net.stubs)

    def get_tile_info_at_site(self, site_name):
        tile_name = self.device_resources.get_tile_name_at_site_name(site_name)
        tile = self.device_resources.tile_name_to_tile[tile_name]
        tile_type = tile.tile_type

        return tile_name, tile_type

    def get_routing_bels(self, tile_types):
        routing_bels = list()

        for tile_type, rbels in self.routing_bels.items():
            if tile_type in tile_types:
                routing_bels += rbels

        return routing_bels

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

            tile_name, tile_type = self.get_tile_info_at_site(site_name)

            bel = placement.bel
            bel_pins = placement.pins
            cell_attr = self.logical_cells_instances.get(cell_name, None)

            self.physical_cells_instances[cell_name] = PhysCellInstance(
                cell_type=cell_type,
                site_name=site_name,
                site_type=site_type,
                tile_name=tile_name,
                tile_type=tile_type,
                bel=bel,
                bel_pins=bel_pins,
                attributes=cell_attr)

    def fill_pip_features(self, pip_feature_format, extra_pip_features,
                          avail_lut_thrus):
        """
        This function generates all features corresponding to the physical routing
        PIPs present in the physical netlist.

        The pip_feature_format argument is required to have a dynamic FASM feature
        formatting, depending on how the specification of the FASM device database.

        where:
            TILE_NAME: is the name of the tile the PIP belongs to
            WIRE0: source PIP wire
            WIRE1: destination PIP wire

        Returns a list containing pseudo PIPs tuple, to be processed by the caller
        The list contains (<tile>, <wire0>, <wire1>) tuples.
        """

        site_thru_pips = list()
        lut_thru_pips = dict()

        for net in self.physical_netlist.nets:
            for segment in self.flattened_nets[net.name]:
                if isinstance(segment, PhysicalPip):
                    tile = segment.tile

                    tile_info = self.device_resources.tile_name_to_tile[tile]
                    tile_type_name = tile_info.tile_type
                    tile_type_index = self.device_resources.tile_name_to_tile[
                        tile].tile_type_index
                    tile_type = self.device_resources.get_tile_type(
                        tile_type_index)

                    wire0 = segment.wire0
                    wire1 = segment.wire1

                    wire0_id = self.device_resources.string_index[wire0]
                    wire1_id = self.device_resources.string_index[wire1]

                    pip = tile_type.pip(wire0_id, wire1_id)
                    if pip.which() != "pseudoCells":
                        if tile_type_name in extra_pip_features:
                            extra_pip_features[tile_type_name].add((tile,
                                                                    wire0))
                            extra_pip_features[tile_type_name].add((tile,
                                                                    wire1))

                        self.add_pip_feature((tile, wire0, wire1),
                                             pip_feature_format)

                        continue

                    # Store LUT-thrus and routing bels used by pseudo tile PIPs
                    for pcell in pip.pseudoCells:
                        site = segment.site
                        assert site

                        bel_name = self.device_resources.strs[pcell.bel]
                        bel, site_type = self.device_resources.get_bel_site_type(
                            site, bel_name)
                        site_type_name = site_type.site_type
                        site_info = self.device_resources.site_name_to_site[
                            site][site_type_name]

                        if bel.category == "sitePort":
                            continue

                        pin = None
                        for bel_pin in bel.yield_pins(site_info,
                                                      Direction.Input):
                            if any(self.device_resources.strs[p] == bel_pin.
                                   name for p in pcell.pins):
                                pin = bel_pin.name

                        assert pin

                        if bel.category == "logic" and bel_name in avail_lut_thrus:
                            _, lut_bel = self.lut_mapper.find_lut_bel(
                                site_type_name, bel_name)

                            key = (net.name, site, bel_name)
                            assert key not in lut_thru_pips

                            lut_thru_pips[key] = {
                                "pin_name": pin,
                                "is_valid": True
                            }

                        elif bel.category == "routing":
                            if tile_type_name not in self.routing_bels:
                                self.routing_bels[tile_type_name] = list()

                            self.routing_bels[tile_type_name].append(
                                (site, bel_name, pin, False))

                    site_thru_pips.append((tile, wire0, wire1))

                # Check and store for site LUT-thrus
                elif isinstance(segment, PhysicalBelPin):
                    bel = segment.bel

                    if bel not in avail_lut_thrus:
                        continue

                    pin = segment.pin
                    site = segment.site
                    site_type = list(self.device_resources.
                                     site_name_to_site[site].keys())[0]
                    _, lut_bel = self.lut_mapper.find_lut_bel(site_type, bel)

                    key = (net.name, site, bel)
                    """
                    A LUT-thru pip is present when both I/O pins are used for a
                    specific BEL at a specific site, for a given net.

                    If the key is not encountered twice, there is no LUT-thru
                    corresponding to the LUT BEL in question.
                    """
                    if key not in lut_thru_pips:
                        lut_thru_pips[key] = {
                            "pin_name": pin,
                            "is_valid": False
                        }
                    elif lut_bel.out_pin == pin:
                        lut_thru_pips[key]["is_valid"] = True

                # Store routing bels
                elif isinstance(segment, PhysicalSitePip):
                    site = segment.site
                    _, tile_type = self.get_tile_info_at_site(site)

                    bel = segment.bel
                    pin = segment.pin
                    is_inverting = segment.is_inverting

                    if tile_type not in self.routing_bels:
                        self.routing_bels[tile_type] = list()

                    self.routing_bels[tile_type].append((site, bel, pin,
                                                         is_inverting))

        return site_thru_pips, lut_thru_pips

    def fill_features(self):
        """
        Function to fill the FASM features.

        Needs to be implemented by the children classes.
        """
        pass

    def output_fasm(self, fasm_file):
        """
        Outputs FASM features that were filled during the fill_features call
        """

        with open(fasm_file, "w") as f:
            print(self.get_origin_line(), file=f)
            for cell_feature in sorted(list(self.cells_features)):
                print(cell_feature, file=f)

            for routing_pip in sorted(list(self.pips_features)):
                print(routing_pip, file=f)
