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

from fpga_interchange import get_version
from fpga_interchange.fasm_generators.luts import LutMapper
from fpga_interchange.logical_netlist import Direction
from fpga_interchange.physical_netlist import PhysicalPip, PhysicalSitePip, PhysicalBelPin
from fpga_interchange.route_stitching import flatten_segments

PhysCellInstance = namedtuple(
    'CellInstance',
    'cell_type site_name site_type tile_name tile_type bel bel_pins attributes'
)


def invert_bitstring(string):
    """ This function inverts all bits in a bitstring. """
    return string.replace("1", "2").replace("0", "1").replace("2", "0")


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
        self.bel_pins_annotations = dict()

        self.annotations = dict()
        self.pips_features = set()
        self.cells_features = set()

        self.lut_mapper = LutMapper(self.device_resources)

    def get_origin_line(self):
        version = get_version()

        return "# Created by the FPGA Interchange FASM Generator (v{})".format(
            version)

    def add_annotation(self, key, value):
        self.annotations[key] = value

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

    def get_all_bel_pins_annotation(self):
        return self.bel_pins_annotations

    def get_bel_pins_annotation(self, tile_name, bel_name):
        """
        Returns a dictionary with BEL pins net assignments. If such (tile, bel)
        does not exist in the design then an empty dict is returned. If a BEL
        pin is not present in the dict then it is unconnected.
        """

        # Filter data
        bel_pins = [p for k, p in self.bel_pins_annotations.items() if \
                    (k[0], k[2]) == (tile_name, bel_name)]
        assert len(bel_pins) <= 1, bel_pins

        # No bel
        if not bel_pins:
            return dict()

        return bel_pins[0]

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

            if cell_attr is None:
                # If no attrs were found, this cell may be part of a macro
                # expansion. Check if this may be the case
                for _, _, macro_cell_name in self.device_resources.get_macro_instances(
                ):
                    if cell_type != macro_cell_name:
                        continue

                    orig_cell_name = cell_name.split("/")[0]
                    cell_attr = self.logical_cells_instances.get(
                        orig_cell_name, None)

                    assert cell_attr, cell_name
                    break

            self.physical_cells_instances[cell_name] = PhysCellInstance(
                cell_type=cell_type,
                site_name=site_name,
                site_type=site_type,
                tile_name=tile_name,
                tile_type=tile_type,
                bel=bel,
                bel_pins=bel_pins,
                attributes=cell_attr)

    def fill_pip_features(self,
                          pip_feature_format,
                          extra_pip_features,
                          avail_lut_thrus,
                          wire_rename=lambda x: x):
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
                    tile = tile_info.sub_tile_prefices[pip.subTile]
                    if pip.which() != "pseudoCells":
                        if tile_type_name in extra_pip_features:
                            extra_pip_features[tile_type_name].add(
                                (tile, wire0, wire1))

                        self.add_pip_feature(
                            (tile, wire_rename(wire0), wire_rename(wire1)),
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

                        if pin == None:
                            # GND/VCC driver LUT has no input pin
                            assert bel_name in avail_lut_thrus, bel_name
                            key = (net.name, site, bel_name)
                            assert key not in lut_thru_pips

                            lut_thru_pips[key] = {
                                "pin_name": None,
                                "is_valid": True
                            }
                            continue

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

                # Check and store for site LUT-thrus and BEL pin nets
                elif isinstance(segment, PhysicalBelPin):
                    bel = segment.bel
                    pin = segment.pin
                    site = segment.site
                    site_type = list(self.device_resources.
                                     site_name_to_site[site].keys())[0]
                    tile, tile_type = self.get_tile_info_at_site(site)

                    # Got a LUT-thru
                    if bel in avail_lut_thrus:
                        _, lut_bel = self.lut_mapper.find_lut_bel(
                            site_type, bel)

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

                        continue

                    # Store BEL pin net annotations
                    key = (tile, site, bel)
                    if key not in self.bel_pins_annotations:
                        self.bel_pins_annotations[key] = dict()

                    self.bel_pins_annotations[key][pin] = net.name

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
            for key, value in sorted(
                    self.annotations.items(), key=lambda x: x[0]):
                print('{{ {}="{}" }}'.format(key, value), file=f)

            for cell_feature in sorted(list(self.cells_features)):
                print(cell_feature, file=f)

            for routing_pip in sorted(list(self.pips_features)):
                print(routing_pip, file=f)
