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

import argparse
import math

from fpga_interchange.logical_netlist import Library, Cell, Direction, CellInstance, LogicalNetlist
from fpga_interchange.interchange_capnp import Interchange, CompressionFormat, write_capnp_file
from fpga_interchange.parameter_definitions import ParameterFormat

from fpga_interchange.testarch_generators.device_resources_builder import BelCategory, ConstantType
from fpga_interchange.testarch_generators.device_resources_builder import DeviceResources, DeviceResourcesCapnp

from fpga_interchange.testarch_generators.device_resources_builder import CellBelMapping, CellBelMappingEntry, Parameter, LutBel

# =============================================================================


class TestArchGenerator():
    """
    Test architecture generator
    """

    def __init__(self, args):
        self.device = DeviceResources()

        self.grid_size = (10, 10)

        # Number of connections within tiles
        self.num_intra_nodes = 16
        # Number of connections between tiles
        self.num_inter_nodes = 8

        self.args = args

    def make_slice_site_type(self):
        """
        Generates a simple SLICE site type.
        """

        # The site
        site_type = self.device.add_site_type("SLICE")

        # Site pins (with BELs added automatically)
        site_type.add_pin("L0_0", Direction.Input,
                          (None, 2e-16, None, None, None, None))
        site_type.add_pin("L1_0", Direction.Input,
                          (None, 2e-16, None, None, None, None))
        site_type.add_pin("L2_0", Direction.Input,
                          (None, 2e-16, None, None, None, None))
        site_type.add_pin("L3_0", Direction.Input,
                          (None, 2e-16, None, None, None, None))
        site_type.add_pin("O_0", Direction.Output,
                          (None, 1.7, None, None, None, None))

        site_type.add_pin("R_0", Direction.Input,
                          (None, 2e-16, None, None, None, None))
        site_type.add_pin("D_0", Direction.Input,
                          (None, 2e-16, None, None, None, None))
        site_type.add_pin("Q_0", Direction.Output,
                          (None, 1.9, None, None, None, None))

        site_type.add_pin("L0_1", Direction.Input,
                          (None, 2e-16, None, None, None, None))
        site_type.add_pin("L1_1", Direction.Input,
                          (None, 2e-16, None, None, None, None))
        site_type.add_pin("L2_1", Direction.Input,
                          (None, 2e-16, None, None, None, None))
        site_type.add_pin("L3_1", Direction.Input,
                          (None, 2e-16, None, None, None, None))
        site_type.add_pin("O_1", Direction.Output,
                          (None, 1.7, None, None, None, None))

        site_type.add_pin("R_1", Direction.Input,
                          (None, 2e-16, None, None, None, None))
        site_type.add_pin("D_1", Direction.Input,
                          (None, 2e-16, None, None, None, None))
        site_type.add_pin("Q_1", Direction.Output,
                          (None, 1.9, None, None, None, None))

        # Unique clock input
        site_type.add_pin("CLK", Direction.Input,
                          (None, 2e-16, None, None, None, None))

        # LUT4 BEL
        a_lut_bel = LutBel("ALUT", ["A1", 'A2', 'A3', 'A4'], 'O', 0, 15)
        b_lut_bel = LutBel("BLUT", ["A1", 'A2', 'A3', 'A4'], 'O', 0, 15)

        site_type.add_lut_element(16, a_lut_bel)
        site_type.add_lut_element(16, b_lut_bel)

        bel_lut = site_type.add_bel("ALUT", "LUT4", BelCategory.LOGIC)
        bel_lut.add_pin("A1", Direction.Input)
        bel_lut.add_pin("A2", Direction.Input)
        bel_lut.add_pin("A3", Direction.Input)
        bel_lut.add_pin("A4", Direction.Input)
        bel_lut.add_pin("O", Direction.Output)

        bel_lut = site_type.add_bel("BLUT", "LUT4", BelCategory.LOGIC)
        bel_lut.add_pin("A1", Direction.Input)
        bel_lut.add_pin("A2", Direction.Input)
        bel_lut.add_pin("A3", Direction.Input)
        bel_lut.add_pin("A4", Direction.Input)
        bel_lut.add_pin("O", Direction.Output)

        # DFF BEL
        bel_ff = site_type.add_bel("AFF", "DFF", BelCategory.LOGIC)
        bel_ff.add_pin("SR", Direction.Input)
        bel_ff.add_pin("C", Direction.Input)
        bel_ff.add_pin("D", Direction.Input)
        bel_ff.add_pin("Q", Direction.Output)

        bel_ff = site_type.add_bel("BFF", "DFF", BelCategory.LOGIC)
        bel_ff.add_pin("SR", Direction.Input)
        bel_ff.add_pin("C", Direction.Input)
        bel_ff.add_pin("D", Direction.Input)
        bel_ff.add_pin("Q", Direction.Output)

        if not self.args.no_ffmux:
            bel_mux = site_type.add_bel("AFFMUX", "MUX2", BelCategory.ROUTING)
            bel_mux.add_pin("I0", Direction.Input)
            bel_mux.add_pin("I1", Direction.Input)
            bel_mux.add_pin("O", Direction.Output)

            bel_mux = site_type.add_bel("BFFMUX", "MUX2", BelCategory.ROUTING)
            bel_mux.add_pin("I0", Direction.Input)
            bel_mux.add_pin("I1", Direction.Input)
            bel_mux.add_pin("O", Direction.Output)

        # LUT wires
        w = site_type.add_wire("L0_0_to_A1", [("L0_0", "L0_0"),
                                              ("ALUT", "A1")])
        w = site_type.add_wire("L1_0_to_A2", [("L1_0", "L1_0"),
                                              ("ALUT", "A2")])
        w = site_type.add_wire("L2_0_to_A3", [("L2_0", "L2_0"),
                                              ("ALUT", "A3")])
        w = site_type.add_wire("L3_0_to_A4", [("L3_0", "L3_0"),
                                              ("ALUT", "A4")])

        w = site_type.add_wire("L0_1_to_A1", [("L0_1", "L0_1"),
                                              ("BLUT", "A1")])
        w = site_type.add_wire("L1_1_to_A2", [("L1_1", "L1_1"),
                                              ("BLUT", "A2")])
        w = site_type.add_wire("L2_1_to_A3", [("L2_1", "L2_1"),
                                              ("BLUT", "A3")])
        w = site_type.add_wire("L3_1_to_A4", [("L3_1", "L3_1"),
                                              ("BLUT", "A4")])

        # FF wires
        w = site_type.add_wire("RST_0", [("R_0", "R_0"), ("AFF", "SR")])
        w = site_type.add_wire("RST_1", [("R_1", "R_1"), ("BFF", "SR")])

        if not self.args.no_ffmux:
            w = site_type.add_wire("DIN_0", [("D_0", "D_0"), ("AFFMUX", "I1")])
            w = site_type.add_wire("DIN_1", [("D_1", "D_1"), ("BFFMUX", "I1")])

        # Clock wire
        w = site_type.add_wire("CLK", [("CLK", "CLK"), ("AFF", "C"),
                                       ("BFF", "C")])

        w = site_type.add_wire("ALUT_O")
        w.connect_to_bel_pin("ALUT", "O")
        w.connect_to_bel_pin("O_0", "O_0")

        if not self.args.no_ffmux:
            w.connect_to_bel_pin("AFFMUX", "I0")
        else:
            w.connect_to_bel_pin("AFF", "D")

        w = site_type.add_wire("BLUT_O")
        w.connect_to_bel_pin("BLUT", "O")
        w.connect_to_bel_pin("O_1", "O_1")

        if not self.args.no_ffmux:
            w.connect_to_bel_pin("BFFMUX", "I0")
        else:
            w.connect_to_bel_pin("BFF", "D")

        if not self.args.no_ffmux:
            w = site_type.add_wire("AMUX_O")
            w.connect_to_bel_pin("AFFMUX", "O")
            w.connect_to_bel_pin("AFF", "D")

            w = site_type.add_wire("BMUX_O")
            w.connect_to_bel_pin("BFFMUX", "O")
            w.connect_to_bel_pin("BFF", "D")

        w = site_type.add_wire("AFF_OUT", [("AFF", "Q"), ("Q_0", "Q_0")])
        w = site_type.add_wire("BFF_OUT", [("BFF", "Q"), ("Q_1", "Q_1")])

        # Site PIPs
        if not self.args.no_ffmux:
            site_type.add_pip(("AFFMUX", "I0"), ("AFFMUX", "O"),
                              (None, 5e-12, None, None, None, None))
            site_type.add_pip(("AFFMUX", "I1"), ("AFFMUX", "O"),
                              (None, 5e-12, None, None, None, None))

            site_type.add_pip(("BFFMUX", "I0"), ("BFFMUX", "O"),
                              (None, 5e-12, None, None, None, None))
            site_type.add_pip(("BFFMUX", "I1"), ("BFFMUX", "O"),
                              (None, 5e-12, None, None, None, None))

        site_type.add_pip(("ALUT", "A1"), ("ALUT", "O"),
                          (None, 5e-12, None, None, None, None))
        site_type.add_pip(("ALUT", "A2"), ("ALUT", "O"),
                          (None, 5e-12, None, None, None, None))
        site_type.add_pip(("ALUT", "A3"), ("ALUT", "O"),
                          (None, 5e-12, None, None, None, None))
        site_type.add_pip(("ALUT", "A4"), ("ALUT", "O"),
                          (None, 5e-12, None, None, None, None))

        site_type.add_pip(("BLUT", "A1"), ("BLUT", "O"),
                          (None, 5e-12, None, None, None, None))
        site_type.add_pip(("BLUT", "A2"), ("BLUT", "O"),
                          (None, 5e-12, None, None, None, None))
        site_type.add_pip(("BLUT", "A3"), ("BLUT", "O"),
                          (None, 5e-12, None, None, None, None))
        site_type.add_pip(("BLUT", "A4"), ("BLUT", "O"),
                          (None, 5e-12, None, None, None, None))

    def make_iob_site_type(self):
        """ Generates the IO site types, with different internal structures.

            - IPAD: only input PAD
            - OPAD: only output PAD
            - IOPAD: both input and output PAD
        """

        ipad = "IPAD"
        opad = "OPAD"
        iopad = "IOPAD"

        for pad in [ipad, opad, iopad]:
            # The site
            site_type = self.device.add_site_type(pad)

            is_inpad = pad in [ipad, iopad]
            is_outpad = pad in [opad, iopad]

            # Wires
            wires = [("PAD", "P")]

            if is_inpad:
                site_type.add_pin("I", Direction.Output)
                site_type.add_pin("NO_BUF_I", Direction.Output)

                bel_ib = site_type.add_bel("IB", "IB", BelCategory.LOGIC)
                bel_ib.add_pin("I", Direction.Output)
                bel_ib.add_pin("P", Direction.Input)

                site_type.add_wire("I", [("IB", "I"), ("I", "I")])

                wires.append(("IB", "P"))
                wires.append(("NO_BUF_I", "NO_BUF_I"))

            if is_outpad:
                site_type.add_pin("O", Direction.Input)

                bel_ob = site_type.add_bel("OB", "OB", BelCategory.LOGIC)
                bel_ob.add_pin("O", Direction.Input)
                bel_ob.add_pin("P", Direction.Output)

                site_type.add_wire("O", [("OB", "O"), ("O", "O")])

                wires.append(("OB", "P"))

            bel_pad = site_type.add_bel("PAD", "PAD", BelCategory.LOGIC)
            bel_pad.add_pin("P", Direction.Inout)

            site_type.add_wire("P", wires)

    def make_power_site_type(self):

        # The site
        site_type = self.device.add_site_type("POWER")

        # Site pins (with BELs added automatically)
        site_type.add_pin("V", Direction.Output)
        site_type.add_pin("G", Direction.Output)

        # VCC bel
        bel_vcc = site_type.add_bel("VCC", "VCC", BelCategory.LOGIC)
        bel_vcc.add_pin("V", Direction.Output)
        self.device.add_const_source(site_type.name, bel_vcc.name, 'V', 'VCC')

        # GND bel
        bel_gnd = site_type.add_bel("GND", "GND", BelCategory.LOGIC)
        bel_gnd.add_pin("G", Direction.Output)
        self.device.add_const_source(site_type.name, bel_gnd.name, 'G', 'GND')

        # Wires
        site_type.add_wire("V", [("VCC", "V"), ("V", "V")])
        site_type.add_wire("G", [("GND", "G"), ("G", "G")])

    def make_tile_type(self, tile_type_name, site_types):
        """
        Generates a simple CLB tile type
        """

        # The tile
        tile_type = self.device.add_tile_type(tile_type_name)

        # Sites and stuff
        for site_type_name in site_types:
            site_type = self.device.site_types[site_type_name]

            # Add the site
            site = tile_type.add_site(site_type.name)

            # Add tile wires for the site and site pin to tile wire mapping
            for pin in site_type.pins.values():

                if pin.direction == Direction.Input:
                    wire_name = "TO_{}_{}".format(site.ref, pin.name.upper())
                elif pin.direction == Direction.Output:
                    wire_name = "FROM_{}_{}".format(site.ref, pin.name.upper())
                else:
                    assert False

                tile_type.add_wire(wire_name, ("Tile-Site", "general"))
                site.primary_pins_to_tile_wires[pin.name] = wire_name

        if tile_type_name == "NULL":
            return
        # Add tile wires for intra nodes
        for i in range(self.num_intra_nodes):
            name = "INTRA_{}".format(i)
            tile_type.add_wire(name, ("Local", "general"))

        # Add tile wires for incoming and outgoin inter-tile connections
        for direction in ["N", "S", "E", "W"]:

            for i in range(self.num_inter_nodes):
                name = "OUT_{}_{}".format(direction, i)
                tile_type.add_wire(name, ("Interconnect", "general"))

            for i in range(self.num_inter_nodes):
                name = "INP_{}_{}".format(direction, i)
                tile_type.add_wire(name, ("Interconnect", "general"))

        # Add PIPs that connect tile wires for the site with intra wires
        wires_for_site = [w for w in tile_type.wires if w.startswith("TO_")]
        for dst_wire in wires_for_site:
            for i in range(self.num_intra_nodes):
                src_wire = "INTRA_{}".format(i)
                tile_type.add_pip(
                    src_wire, dst_wire, "intraTilePIP", is_buffered21=False)

        wires_for_site = [w for w in tile_type.wires if w.startswith("FROM_")]
        for src_wire in wires_for_site:
            for i in range(self.num_intra_nodes):
                dst_wire = "INTRA_{}".format(i)
                tile_type.add_pip(
                    src_wire, dst_wire, "intraTilePIP", is_buffered21=False)

        # Input tile wires to intra wires and vice-versa
        for direction in ["N", "S", "E", "W"]:
            for i in range(self.num_inter_nodes):

                src_wire = "INP_{}_{}".format(direction, i)
                for j in range(self.num_intra_nodes):
                    dst_wire = "INTRA_{}".format(j)
                    tile_type.add_pip(src_wire, dst_wire, "tilePIP")

                dst_wire = "OUT_{}_{}".format(direction, i)
                for j in range(self.num_intra_nodes):
                    src_wire = "INTRA_{}".format(j)
                    tile_type.add_pip(src_wire, dst_wire, "tilePIP")

        if tile_type_name == "PWR":
            tile_type.add_const_source(ConstantType.VCC, "FROM_POWER0_V")
            tile_type.add_const_source(ConstantType.GND, "FROM_POWER0_G")
        # TODO: const. wires

    def make_device_grid(self):
        width = self.grid_size[0] - 1
        height = self.grid_size[1] - 1

        for y in range(height + 1):
            for x in range(width + 1):
                is_0_0 = x == 0 and y == 0

                is_corner = is_0_0 or \
                            x == 0 and y == height or \
                            x == width and y == 0 or \
                            x == width and y == height

                is_left = x == 0
                is_right = x == height
                is_top_bottom = y in [0, width]

                is_centre = y == height // 2 and x == width // 2

                suffix = "_X{}Y{}".format(x, y)

                if is_0_0:
                    self.device.add_tile("NULL", "NULL", (x, y))
                elif is_top_bottom and not is_corner:
                    self.device.add_tile("IOB" + suffix, "IOB", (x, y))
                elif is_left:
                    self.device.add_tile("IB" + suffix, "IB", (x, y))
                elif is_right:
                    self.device.add_tile("OB" + suffix, "OB", (x, y))
                elif is_centre:
                    self.device.add_tile("PWR" + suffix, "PWR", (x, y))
                else:
                    self.device.add_tile("CLB" + suffix, "CLB", (x, y))

    def make_wires_and_nodes(self):

        # Add wires for all tiles
        for tile_name in self.device.tiles_by_name:
            self.device.add_wires_for_tile(tile_name)

        # Add nodes for internal tile wires
        for tile in self.device.tiles.values():
            tile_type = self.device.tile_types[tile.type]

            for wire in tile_type.wires:
                if wire.startswith("TO_") or wire.startswith("FROM_"):
                    wire_id = self.device.get_wire_id(tile.name, wire)
                    self.device.add_node([wire_id], "toSite")
                elif wire.startswith("INTRA_"):
                    wire_id = self.device.get_wire_id(tile.name, wire)
                    self.device.add_node([wire_id], "internal")

        # Add nodes for inter-tile connections.
        def offset_loc(pos, ofs):
            return (pos[0] + ofs[0], pos[1] + ofs[1])

        for loc, tile_id in self.device.tiles_by_loc.items():
            if loc == (0, 0):
                continue
            tile = self.device.tiles[tile_id]
            tile_type = self.device.tile_types[tile.type]

            OPPOSITE = {
                "N": "S",
                "S": "N",
                "E": "W",
                "W": "E",
            }

            for direction, offset in [("N", (0, +1)), ("S", (0, -1)),
                                      ("E", (-1, 0)), ("W", (+1, 0))]:

                for i in range(self.num_inter_nodes):
                    wire_name = "INP_{}_{}".format(direction, i)
                    wire_ids = [self.device.get_wire_id(tile.name, wire_name)]

                    other_loc = offset_loc(loc, offset)
                    if other_loc == (0, 0):
                        continue
                    if other_loc[0] >= 0 and other_loc[0] < self.grid_size[0] and \
                       other_loc[1] >= 0 and other_loc[1] < self.grid_size[1]:

                        other_tile_id = self.device.tiles_by_loc[other_loc]
                        other_tile = self.device.tiles[other_tile_id]
                        other_wire_name = "OUT_{}_{}".format(
                            OPPOSITE[direction], i)

                        wire_ids.append(
                            self.device.get_wire_id(other_tile.name,
                                                    other_wire_name))
                    self.device.add_node(wire_ids, "external")

    def make_package_data(self):

        package = self.device.add_package(self.args.package)

        iopad_id = 0
        ipad_id = 0
        opad_id = 0
        for site in self.device.sites.values():
            if site.type == "IOPAD":
                pad_name = f"IO_{iopad_id}"
                iopad_id += 1
            elif site.type == "OPAD":
                pad_name = f"O_{opad_id}"
                opad_id += 1
            elif site.type == "IPAD":
                pad_name = f"I_{ipad_id}"
                ipad_id += 1
            else:
                continue

            package.add_pin(pad_name, site.name, "PAD")

    def make_primitives_library(self):

        # Primitives library
        library = Library("primitives")
        self.device.cell_libraries["primitives"] = library

        def make_luts(max_size):
            for lut_size in range(1, max_size + 1):
                name = f"LUT{lut_size}"
                init = f"{2 ** lut_size}'h0"
                cell = Cell(name=name, property_map={"INIT": init})

                print(name, init)

                in_ports = list()
                for port in range(lut_size):
                    port_name = f"I{port}"
                    cell.add_port(port_name, Direction.Input)
                    in_ports.append(port_name)

                cell.add_port("O", Direction.Output)
                library.add_cell(cell)

                param = Parameter("INIT", ParameterFormat.VERILOG_HEX, init)
                self.device.add_parameter(name, param)
                self.device.add_lut_cell(name, in_ports, 'INIT')

        make_luts(4)

        def make_dffs(rst_types):
            for rst_type in rst_types:
                cell = Cell(f"DFF{rst_type}")
                cell.add_port("D", Direction.Input)
                cell.add_port(rst_type, Direction.Input)
                cell.add_port("C", Direction.Input)
                cell.add_port("Q", Direction.Output)
                library.add_cell(cell)

        make_dffs(["S", "R"])

        cell = Cell("IB")
        cell.add_port("I", Direction.Output)
        cell.add_port("P", Direction.Input)
        library.add_cell(cell)

        cell = Cell("OB")
        cell.add_port("O", Direction.Input)
        cell.add_port("P", Direction.Output)
        library.add_cell(cell)

        cell = Cell("VCC")
        cell.add_port("V", Direction.Output)
        library.add_cell(cell)

        cell = Cell("GND")
        cell.add_port("G", Direction.Output)
        library.add_cell(cell)

        # Macros library
        library = Library("macros")
        self.device.cell_libraries["macros"] = library

    def make_cell_bel_mappings(self):

        # TODO: Pass all the information via device.add_cell_bel_mapping()
        delay_mapping = [
            ('A1', 'O', (None, 50e-12, None, None, None, None), 'comb'),
            ('A2', 'O', (None, 50e-12, None, None, None, None), 'comb'),
            ('A3', 'O', (None, 50e-12, None, None, None, None), 'comb'),
            ('A4', 'O', (None, 50e-12, None, None, None, None), 'comb'),
        ]

        def make_lut_mapping(max_size):
            bel_pins = [f"A{pin}" for pin in range(1, max_size + 1)]
            cell_pins = [f"I{pin}" for pin in range(max_size)]

            for lut_size in range(1, max_size + 1):
                name = f"LUT{lut_size}"
                pin_map = dict(
                    zip(cell_pins[0:lut_size], bel_pins[0:lut_size]))
                pin_map["O"] = "O"

                mapping = CellBelMapping(name)
                mapping.entries.append(
                    CellBelMappingEntry(
                        site_type="SLICE",
                        bels=["ALUT", "BLUT"],
                        pin_map=pin_map,
                        delay_mapping=delay_mapping[0:lut_size]))

                self.device.add_cell_bel_mapping(mapping)

        make_lut_mapping(4)

        delay_mapping = [
            ('D', ('C', 'rise'), (None, 5e-12, None, None, None, None),
             'setup'),
            ('D', ('C', 'rise'), (None, 8e-12, None, None, None, None),
             'hold'),
            (('C', 'rise'), 'Q', (None, 6e-12, None, None, None, None),
             'clk2q'),
            ('SR', 'Q', (None, 24e-12, None, None, None, None), 'comb'),
        ]

        def make_dff_mapping(rst_types):
            for rst_type in rst_types:
                mapping = CellBelMapping(f"DFF{rst_type}")
                mapping.entries.append(
                    CellBelMappingEntry(
                        site_type="SLICE",
                        bels=["AFF", "BFF"],
                        pin_map={
                            "D": "D",
                            rst_type: "SR",
                            "C": "C",
                            "Q": "Q",
                        },
                        delay_mapping=delay_mapping))
                self.device.add_cell_bel_mapping(mapping)

        make_dff_mapping(["S", "R"])

        mapping = CellBelMapping("IB")
        mapping.entries.append(
            CellBelMappingEntry(
                site_type="IOPAD", bels=["IB"], pin_map={
                    "I": "I",
                    "P": "P",
                }))
        self.device.add_cell_bel_mapping(mapping)

        mapping = CellBelMapping("OB")
        mapping.entries.append(
            CellBelMappingEntry(
                site_type="IOPAD", bels=["OB"], pin_map={
                    "O": "O",
                    "P": "P",
                }))
        self.device.add_cell_bel_mapping(mapping)

        mapping = CellBelMapping("GND")
        mapping.entries.append(
            CellBelMappingEntry(
                site_type="POWER", bels=["GND"], pin_map={
                    "G": "G",
                }))
        self.device.add_cell_bel_mapping(mapping)

        mapping = CellBelMapping("VCC")
        mapping.entries.append(
            CellBelMappingEntry(
                site_type="POWER", bels=["VCC"], pin_map={
                    "V": "V",
                }))
        self.device.add_cell_bel_mapping(mapping)

    def make_parameters(self):
        pass

    def generate(self):
        self.make_iob_site_type()
        self.make_slice_site_type()
        self.make_power_site_type()

        self.make_tile_type("CLB", ["SLICE", "SLICE"])
        self.make_tile_type("IOB", ["IOPAD"])
        self.make_tile_type("IB", ["IPAD"])
        self.make_tile_type("OB", ["OPAD"])
        self.make_tile_type("PWR", ["POWER"])
        self.make_tile_type("NULL", [])

        self.make_device_grid()
        self.make_wires_and_nodes()

        self.make_package_data()

        self.make_primitives_library()
        self.make_cell_bel_mappings()
        self.make_parameters()

        # Add pip imings
        # Values are taken at random, resisitance, input and output capacitance are chosen
        # to be samewhat inline with values calculated from skaywater PDK
        self.device.add_PIPTiming("tilePIP", 3e-16, 1e-16, 5e-10, 0.5, 4e-16)
        self.device.add_PIPTiming("intraTilePIP", 1e-16, 4e-17, 3e-10, 0.1,
                                  2e-16)

        # Add node timing
        # Value taken from skywater PDK for metal layer 1,
        # Tile-to-Tile length 30 um, internal 15 um and to site 2 um
        # Wire width of 0.14 um
        self.device.add_nodeTiming("external", 26.8, 1.14e-14)
        self.device.add_nodeTiming("internal", 13.4, 5.7e-15)
        self.device.add_nodeTiming("toSite", 1.8, 7.6e-16)

        self.device.print_stats()


# =============================================================================


def main():

    parser = argparse.ArgumentParser(description="Generates testarch FPGA")
    parser.add_argument(
        "--schema-dir",
        required=True,
        help="Path to FPGA interchange capnp schema files")
    parser.add_argument(
        "--out-file", default="test_arch.device", help="Output file name")
    parser.add_argument("--package", default="TESTPKG", help="Package name")
    parser.add_argument(
        "--no-ffmux",
        action="store_true",
        help=
        "Do not add the mux that selects FF input forcing it to require LUT-thru"
    )

    args = parser.parse_args()

    # Run the test architecture generator
    gen = TestArchGenerator(args)
    gen.generate()

    # Initialize the writer (or "serializer")
    interchange = Interchange(args.schema_dir)
    writer = DeviceResourcesCapnp(
        gen.device,
        interchange.device_resources_schema,
        interchange.logical_netlist_schema,
    )

    # Serialize
    device_resources = writer.to_capnp()
    with open(args.out_file, "wb") as fp:
        write_capnp_file(
            device_resources,
            fp)  #, compression_format=CompressionFormat.UNCOMPRESSED)


# =============================================================================

if __name__ == "__main__":
    main()
