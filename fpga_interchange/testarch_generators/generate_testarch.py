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

    def __init__(self, package):
        self.device = DeviceResources()

        self.grid_size = (10, 10)
        self.num_intra_nodes = 8
        self.num_inter_nodes = 8

        self.package = package

    def make_slice_site_type(self):
        """
        Generates a simple SLICE site type.
        """

        # The site
        site_type = self.device.add_site_type("SLICE")

        # Site pins (with BELs added automatically)
        site_type.add_pin("L0", Direction.Input,
                          (None, 2e-16, None, None, None, None))
        site_type.add_pin("L1", Direction.Input,
                          (None, 2e-16, None, None, None, None))
        site_type.add_pin("L2", Direction.Input,
                          (None, 2e-16, None, None, None, None))
        site_type.add_pin("L3", Direction.Input,
                          (None, 2e-16, None, None, None, None))
        site_type.add_pin("O", Direction.Output,
                          (None, 1.7, None, None, None, None))

        site_type.add_pin("R", Direction.Input,
                          (None, 2e-16, None, None, None, None))
        site_type.add_pin("C", Direction.Input,
                          (None, 2e-16, None, None, None, None))
        site_type.add_pin("D", Direction.Input,
                          (None, 2e-16, None, None, None, None))
        site_type.add_pin("Q", Direction.Output,
                          (None, 1.9, None, None, None, None))

        # LUT4 BEL
        bel_lut = site_type.add_bel("LUT", "LUT4", BelCategory.LOGIC)
        bel_lut.add_pin("I0", Direction.Input)
        bel_lut.add_pin("I1", Direction.Input)
        bel_lut.add_pin("I2", Direction.Input)
        bel_lut.add_pin("I3", Direction.Input)
        bel_lut.add_pin("O", Direction.Output)

        lut_bel = LutBel("LUT", ["I0", 'I1', 'I2', 'I3'], 'O', 0, 15)

        site_type.addLutElement(16, lut_bel)

        # DFF BEL
        bel_ff = site_type.add_bel("FF", "DFF", BelCategory.LOGIC)
        bel_ff.add_pin("R", Direction.Input)
        bel_ff.add_pin("C", Direction.Input)
        bel_ff.add_pin("D", Direction.Input)
        bel_ff.add_pin("Q", Direction.Output)

        # DFF input mux BEL (routing)
        bel_mux = site_type.add_bel("FFMUX", "MUX2", BelCategory.ROUTING)
        bel_mux.add_pin("I0", Direction.Input)
        bel_mux.add_pin("I1", Direction.Input)
        bel_mux.add_pin("O", Direction.Output)

        # Site wires
        w = site_type.add_wire("L0_to_I0", [("L0", "L0"), ("LUT", "I0")])
        w = site_type.add_wire("L1_to_I1", [("L1", "L1"), ("LUT", "I1")])
        w = site_type.add_wire("L2_to_I2", [("L2", "L2"), ("LUT", "I2")])
        w = site_type.add_wire("L3_to_I3", [("L3", "L3"), ("LUT", "I3")])

        w = site_type.add_wire("RST", [("R", "R"), ("FF", "R")])
        w = site_type.add_wire("CLR", [("C", "C"), ("FF", "C")])
        w = site_type.add_wire("DIN", [("D", "D"), ("FFMUX", "I1")])

        w = site_type.add_wire("LUT_O")
        w.connect_to_bel_pin("LUT", "O")
        w.connect_to_bel_pin("FFMUX", "I0")
        w.connect_to_bel_pin("O", "O")

        w = site_type.add_wire("MUX_O")
        w.connect_to_bel_pin("FFMUX", "O")
        w.connect_to_bel_pin("FF", "D")

        w = site_type.add_wire("FF_OUT", [("FF", "Q"), ("Q", "Q")])

        # Site PIPs
        site_type.add_pip(("FFMUX", "I0"), ("FFMUX", "O"),
                          (None, 5e-12, None, None, None, None))
        site_type.add_pip(("FFMUX", "I1"), ("FFMUX", "O"),
                          (None, 5e-12, None, None, None, None))

    def make_iob_site_type(self):

        # The site
        site_type = self.device.add_site_type("IOPAD")

        # Site pins (with BELs added automatically)
        site_type.add_pin("I", Direction.Output)
        site_type.add_pin("O", Direction.Input)

        # TODO Change to use one pad for both input and output buffers
        # IPAD bel
        bel_ib = site_type.add_bel("IB", "IB", BelCategory.LOGIC)
        bel_ib.add_pin("I", Direction.Output)
        bel_ib.add_pin("P", Direction.Input)

        # OPAD bel
        bel_ob = site_type.add_bel("OB", "OB", BelCategory.LOGIC)
        bel_ob.add_pin("O", Direction.Input)
        bel_ob.add_pin("P", Direction.Output)

        bel_opad = site_type.add_bel("PAD", "PAD", BelCategory.LOGIC)
        bel_opad.add_pin("P", Direction.Inout)

        # Wires
        site_type.add_wire("I", [("IB", "I"), ("I", "I")])
        site_type.add_wire("O", [("OB", "O"), ("O", "O")])
        site_type.add_wire("P", [("IB", "P"), ("OB", "P"), ("PAD", "P")])

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

        for y in range(self.grid_size[1]):
            for x in range(self.grid_size[0]):

                is_0_0 = x == 0 and y == 0
                is_perimeter = y in [0, self.grid_size[1] - 1] or \
                               x in [0, self.grid_size[0] - 1]
                is_centre = y == self.grid_size[
                    1] // 2 and x == self.grid_size[0] // 2

                suffix = "_X{}Y{}".format(x, y)

                if is_0_0:
                    self.device.add_tile("NULL", "NULL", (x, y))
                elif is_perimeter:
                    self.device.add_tile("IOB" + suffix, "IOB", (x, y))
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

        package = self.device.add_package(self.package)

        pad_id = 0
        for site in self.device.sites.values():
            if site.type == "IOPAD":
                package.add_pin("A{}".format(pad_id), site.name, "PAD")
                pad_id += 1

    def make_primitives_library(self):

        # Primitives library
        library = Library("primitives")
        self.device.cell_libraries["primitives"] = library

        cell = Cell(name="LUT", property_map={"INIT": "16'h0000"})
        cell.add_port("A0", Direction.Input)
        cell.add_port("A1", Direction.Input)
        cell.add_port("A2", Direction.Input)
        cell.add_port("A3", Direction.Input)
        cell.add_port("O", Direction.Output)
        library.add_cell(cell)
        param = Parameter("INIT", ParameterFormat.VERILOG_HEX, "16'h0000")
        self.device.add_parameter("LUT", param)
        self.device.add_LutCell("LUT", ['A0', 'A1', 'A2', 'A3'], 'INIT')

        cell = Cell("DFF")
        cell.add_port("D", Direction.Input)
        cell.add_port("R", Direction.Input)
        cell.add_port("C", Direction.Input)
        cell.add_port("Q", Direction.Output)
        library.add_cell(cell)

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
            ('I0', 'O', (None, 50e-12, None, None, None, None), 'comb'),
            ('I1', 'O', (None, 50e-12, None, None, None, None), 'comb'),
            ('I2', 'O', (None, 50e-12, None, None, None, None), 'comb'),
            ('I3', 'O', (None, 50e-12, None, None, None, None), 'comb'),
        ]
        mapping = CellBelMapping("LUT")
        mapping.entries.append(
            CellBelMappingEntry(
                site_type="SLICE",
                bel="LUT",
                pin_map={
                    "A0": "I0",
                    "A1": "I1",
                    "A2": "I2",
                    "A3": "I3",
                    "O": "O",
                },
                delay_mapping=delay_mapping))
        self.device.add_cell_bel_mapping(mapping)

        delay_mapping = [
            ('D', ('C', 'rise'), (None, 5e-12, None, None, None, None),
             'setup'),
            ('D', ('C', 'rise'), (None, 8e-12, None, None, None, None),
             'hold'),
            (('C', 'rise'), 'Q', (None, 6e-12, None, None, None, None),
             'clk2q'),
            ('R', 'Q', (None, 24e-12, None, None, None, None), 'comb'),
        ]
        mapping = CellBelMapping("DFF")
        mapping.entries.append(
            CellBelMappingEntry(
                site_type="SLICE",
                bel="FF",
                pin_map={
                    "D": "D",
                    "R": "R",
                    "C": "C",
                    "Q": "Q",
                },
                delay_mapping=delay_mapping))
        self.device.add_cell_bel_mapping(mapping)

        mapping = CellBelMapping("FFMUX")
        mapping.entries.append(
            CellBelMappingEntry(
                site_type="SLICE",
                bel="FFMUX",
                pin_map={
                    "I0": "I0",
                    "I1": "I1",
                    "O": "O",
                }))
        self.device.add_cell_bel_mapping(mapping)

        mapping = CellBelMapping("IB")
        mapping.entries.append(
            CellBelMappingEntry(
                site_type="IOPAD", bel="IB", pin_map={
                    "I": "I",
                    "P": "P",
                }))
        self.device.add_cell_bel_mapping(mapping)

        mapping = CellBelMapping("OB")
        mapping.entries.append(
            CellBelMappingEntry(
                site_type="IOPAD", bel="OB", pin_map={
                    "O": "O",
                    "P": "P",
                }))
        self.device.add_cell_bel_mapping(mapping)

        mapping = CellBelMapping("GND")
        mapping.entries.append(
            CellBelMappingEntry(
                site_type="POWER", bel="GND", pin_map={
                    "G": "G",
                }))
        self.device.add_cell_bel_mapping(mapping)

        mapping = CellBelMapping("VCC")
        mapping.entries.append(
            CellBelMappingEntry(
                site_type="POWER", bel="VCC", pin_map={
                    "V": "V",
                }))
        self.device.add_cell_bel_mapping(mapping)

    def make_parameters(self):
        pass

    def generate(self):
        self.make_iob_site_type()
        self.make_slice_site_type()
        self.make_power_site_type()

        self.make_tile_type("CLB", ["SLICE"])
        self.make_tile_type("IOB", ["IOPAD"])
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

    args = parser.parse_args()

    # Run the test architecture generator
    gen = TestArchGenerator(args.package)
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
