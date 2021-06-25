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
from enum import Enum
from collections import namedtuple

from fpga_interchange.logical_netlist import Direction
from fpga_interchange.interchange_capnp import output_logical_netlist

# =============================================================================


class BelCategory(Enum):
    LOGIC = 0
    ROUTING = 1
    SITE_PORT = 2


class ConstantType(Enum):
    NO_PREFERENCE = 0
    GND = 1
    VCC = 2


OPPOSITE_DIRECTION = {
    Direction.Input: Direction.Output,
    Direction.Output: Direction.Input,
}


class PackagePin():
    def __init__(self, name, site_name, bel_name):
        self.name = name
        self.site_name = site_name
        self.bel_name = bel_name


class Package():
    def __init__(self, name):
        self.name = name
        self.pins = {}
        # TODO: Speed grades

    def add_pin(self, name, site_name, bel_name):
        """
        Adds a new package pin
        """
        assert name not in self.pins, name
        self.pins[name] = PackagePin(name, site_name, bel_name)


class CellBelMappingEntry():
    def __init__(self, site_type, bel, pin_map):
        self.site_type = site_type
        self.bel = bel
        self.pin_map = pin_map  # dict(cell_pin) -> bel_pin


class CellBelMapping():
    def __init__(self, cell_type, delay_mapping=[]):
        self.cell_type = cell_type
        self.entries = []
        self.delay_mapping = delay_mapping


class BelPin():
    def __init__(self, name, direction):
        self.name = name
        self.direction = direction

    def __repr__(self):
        return "BelPin(\"{}\", {})".format(self.name, self.direction.name)


class Bel():
    def __init__(self, name, type, category):
        self.name = name
        self.type = type
        self.category = category
        self.is_inverting = False  # TODO: FIXME:

        self.pins = {}  # dict(name) -> BelPin

    def add_pin(self, name, direction):
        """
        Adds a pin to the BEL
        """
        assert name not in self.pins, name
        self.pins[name] = BelPin(name, direction)

        return self.pins[name]

    def __repr__(self):
        return "Bel(\"{}\", \"{}\", {})".format(self.name, self.type,
                                                self.category.name)


class SitePin():
    def __init__(self, name, direction, bel_name):
        self.name = name
        self.direction = direction
        self.bel_name = bel_name

    def __repr__(self):
        return "SitePin(\"{}\", {}, bel=\"{}\")".format(
            self.name, self.direction.name, self.bel_name)


class SiteWire():
    def __init__(self, name):
        self.name = name
        self.bel_pins = set()

    def connect_to_bel_pin(self, bel_name, pin_name):
        """
        Connects the wire to the given BEL and its pin. Does not check if the
        given names are legal!
        """
        bel_pin = (bel_name, pin_name)
        assert bel_pin not in self.bel_pins, bel_pin
        self.bel_pins.add(bel_pin)


class SitePip():
    def __init__(self, src_bel_pin, dst_bel_pin):
        self.src_bel_pin = src_bel_pin
        self.dst_bel_pin = dst_bel_pin

    def __repr__(self):
        return "SitePip({}, {})".format(self.src_bel_pin, self.dst_bel_pin)


class SiteType():
    def __init__(self, name):
        self.name = name
        self.pins = {}  # dict(name) -> SitePin
        self.bels = {}  # dict(name) -> Bel
        self.pips = set()
        self.wires = {}  # dict(name) -> SiteWire


#        self.alt_site_types = []

    def add_pin(self, name, direction):
        """
        Adds a pin to the site type along with its corresponding BEL
        """

        # Add BEL
        bel_name = name
        bel = Bel(bel_name, "pin", BelCategory.SITE_PORT)
        assert bel.name not in self.bels, bel.name
        self.bels[bel.name] = bel

        # Add BEL pin
        bel.add_pin(name, OPPOSITE_DIRECTION[direction])

        # Add the site pin
        assert name not in self.pins, name
        self.pins[name] = SitePin(name, direction, bel_name)

        return self.pins[name]

    def add_bel(self, name, type, category):
        """
        Adds a new BEL to the site type
        """
        assert name not in self.bels, name
        self.bels[name] = Bel(name, type, category)

        return self.bels[name]

    def add_wire(self, name, connections=None):
        """
        Adds a new wire to the site type. Connect the wire to BEL pins from
        the given connection list (if any)
        """

        # Add the wire
        assert name not in self.wires, name
        wire = SiteWire(name)
        self.wires[name] = wire

        # Make connections
        if connections:
            for bel_name, pin_name in connections:
                wire.connect_to_bel_pin(bel_name, pin_name)

        return wire

    def add_pip(self, src_bel_pin, dst_bel_pin):
        """
        Adds a new site PIP to the site type
        """
        pip = SitePip(src_bel_pin, dst_bel_pin)
        assert pip not in self.pips, pip
        self.pips.add(pip)

        return pip


class SiteTypeInTileType():
    def __init__(self, ref, type):
        self.ref = ref
        self.type = type

        self.primary_pins_to_tile_wires = {}
        self.alt_pins_to_primary_pins = {}


class PIP():
    def __init__(self,
                 wire0,
                 wire1,
                 delay_type,
                 is_buffered20=True,
                 is_buffered21=True):
        self.wire0 = wire0
        self.wire1 = wire1

        self.is_directional = True
        self.is_buffered20 = is_buffered20  # TODO:
        self.is_buffered21 = is_buffered21

        self.delay_type = delay_type

        # TODO: Pseudo cells


class TileType():
    def __init__(self, name):

        self.name = name

        self.site_types = {}  # dict(name) -> SiteTypeInTileType
        self.wires = set()
        self.pips = set()
        self.constants = {}  # dict(constant) -> set(wire_name)

    def add_site(self, type):
        """
        Adds a new site type instance to the tile type
        """

        # Append index to the site type and use it as a reference
        count = len([s for s in self.site_types.values() if s.type == type])
        ref = "{}{}".format(type, count)

        # Add the instance
        assert ref not in self.site_types, ref
        self.site_types[ref] = SiteTypeInTileType(ref, type)
        return self.site_types[ref]

    def add_wire(self, name):
        """
        Adds a new wire to the tile type
        """
        assert name not in self.wires, name
        self.wires.add(name)

        return name

    def add_pip(self,
                wire0,
                wire1,
                delay_type,
                is_buffered20=True,
                is_buffered21=True):
        """
        Adds a new PIP to the tile type
        """
        pip = PIP(wire0, wire1, delay_type, is_buffered20, is_buffered21)
        assert pip not in self.pips, pip
        self.pips.add(pip)

        return pip

    def add_const_source(self, constant, wire):
        """
        Adds an existing tile wire to the given constant source
        """

        # Add the constant source
        if constant not in self.constants:
            self.constants[constant] = set()

        # Add the wire to it
        assert wire not in self.constants[constant], (constant, wire)
        self.constants[constant].add(wire)


class Site():
    def __init__(self, name, type, ref):
        self.name = name
        self.type = type
        self.ref = ref


class Tile():
    def __init__(self, name, tile_type, loc):
        self.name = name
        self.type = tile_type.name
        self.loc = loc  # as (col, row)

        # Add site instances of site types from the tile type
        self.sites = {}
        for site_type_in_tile_type in tile_type.site_types.values():

            # Make a globally unique site name
            site_name = "{}_X{}Y{}".format(site_type_in_tile_type.ref, loc[0],
                                           loc[1])

            # Add the site
            site = Site(site_name, site_type_in_tile_type.type,
                        site_type_in_tile_type.ref)

            assert site.ref not in self.sites
            self.sites[site.ref] = site


Wire = namedtuple("Wire", "tile wire")

# =============================================================================


class DeviceResources():
    def __init__(self):
        self.name = ""

        # Site and tile types
        self.site_types = {}
        self.tile_types = {}

        # Tiles (instances)
        self.tiles = {}  # dict(id(tile)) -> tile
        self.tiles_by_loc = {}  # dict(loc) -> id(tile)
        self.tiles_by_name = {}  # dict(tile_name) -> id(tile)

        # Site (instances)
        self.sites = {}  # dict(id(site)) -> site
        self.sites_by_name = {}  # dict(site_name) -> id(site)

        # Wires
        self.wires = []
        self.wires_by_tile = {}  # dict(tile_name) -> list(wire_idx)

        # Special string map for wires to save memory
        self.wire_str_list = []
        self.wire_str_map = {}

        # Constant generators
        self.constants = {}

        # Nodes
        self.nodes = []

        # Timing
        self.node_delay_types = {}
        self.pip_delay_types = {}

        # Physical chip packages
        self.packages = {}  # dict(name) -> Package

        # Cell libraries. There should be "primitives" and "macros"
        self.cell_libraries = {}

        # Cell types to BELs mappings
        self.cell_bel_mappings = {}

    def add_site_type(self, name):
        """
        Adds a new site type to the device
        """
        assert name not in self.site_types, name
        self.site_types[name] = SiteType(name)

        return self.site_types[name]

    def add_tile_type(self, name):
        """
        Adds a new tile type to the device
        """
        assert name not in self.tile_types, name
        self.tile_types[name] = TileType(name)

        return self.tile_types[name]

    def add_tile(self, name, type, loc):
        """
        Adds a new tile to the device
        """

        # Get the tile type
        assert type in self.tile_types, type
        tile_type = self.tile_types[type]

        # Create the tile
        tile = Tile(name, tile_type, loc)
        tile_id = id(tile)

        # Add it
        assert tile_id not in self.tiles
        self.tiles[tile_id] = tile

        assert loc not in self.tiles_by_loc, loc
        self.tiles_by_loc[loc] = tile_id

        assert name not in self.tiles_by_name, name
        self.tiles_by_name[name] = tile_id

        # Add all its site instances
        for site in tile.sites.values():
            site_id = id(site)

            assert site_id not in self.sites
            self.sites[site_id] = site

            assert site.name not in self.sites_by_name
            self.sites_by_name[site.name] = site_id

        return tile

    def add_wire(self, tile_name, wire_name):
        """
        Adds a new instance of a tile wire. Returns the global wire index.
        """

        def add_string(s):

            if s not in self.wire_str_map:
                self.wire_str_map[s] = len(self.wire_str_list)
                self.wire_str_list.append(s)

            return self.wire_str_map[s]

        # Create the wire, map strings
        wire = Wire(tile=add_string(tile_name), wire=add_string(wire_name))
        wire_id = len(self.wires)

        # Add the wire
        if tile_name not in self.wires_by_tile:
            self.wires_by_tile[tile_name] = []

        self.wires_by_tile[tile_name].append(wire_id)
        self.wires.append(wire)

        return wire_id

    def add_nodeTiming(self, delay_type, R, C):
        """
        Adds new node delay_type to device based on resistance R and capacitance C
        """

        assert delay_type not in self.node_delay_types, delay_type
        self.node_delay_types[delay_type] = (R, C)

    def add_PIPTiming(self, delay_type, iC, itC, itD, oR, oC):
        """
        Adds new pip delay_type to device based on input capacitance iC,
        internal capacitance itC, internal delay itD,
        output resistance oR and output capacitance oC.

        Internal capacitances are taken into account only if PIP is taken,
        input capacitance is always added to node capacitance.
        """

        assert delay_type not in self.pip_delay_types, delay_type
        self.pip_delay_types[delay_type] = (iC, itC, itD, oR, oC)

    def get_wire(self, wire_id):
        """
        Returns a Wire object containing string literals which refer to the
        tile name and wire name.
        """

        def get_string(i):
            assert i < len(self.wire_str_list), i
            return self.wire_str_list[i]

        assert wire_id < len(self.wires), wire_id

        wire = Wire(
            tile=get_string(self.wires[wire_id].tile),
            wire=get_string(self.wires[wire_id].wire),
        )

        return wire

    def get_wire_id(self, tile_name, wire_name):
        """
        Finds the wire instance and returns its id
        """

        # Get tile wire instances
        assert tile_name in self.wires_by_tile, tile_name
        wire_ids = self.wires_by_tile[tile_name]

        # Find the interesting one
        for wire_id in wire_ids:
            wire = self.get_wire(wire_id)
            if (wire.tile, wire.wire) == (tile_name, wire_name):
                return wire_id

        # Not found
        assert False, (tile_name, wire_name)

    def add_wires_for_tile(self, tile_name):
        """
        Instantiates all wires of the tile type of the given tile instance.
        """

        # Get the tile
        assert tile_name in self.tiles_by_name, tile_name
        tile_id = self.tiles_by_name[tile_name]
        tile = self.tiles[tile_id]

        # Get the tile type
        assert tile.type in self.tile_types, tile.type
        tile_type = self.tile_types[tile.type]

        # Add all wires
        for wire in tile_type.wires:
            self.add_wire(tile_name, wire)

    def add_const_source(self, site_name, bel_name, bel_port, constant):
        assert (site_name, bel_name,
                bel_port) not in self.constants, (site_name, bel_name,
                                                  bel_port)
        self.constants[(site_name, bel_name, bel_port)] = constant

    def add_node(self, wire_ids, node_type):
        """
        Adds a new node that spans the given wire ids.
        """
        self.nodes.append((wire_ids, node_type))

    def add_package(self, name):
        """
        Adds a new chip package for the device. Returns the Package object
        """
        assert name not in self.packages, name
        self.packages[name] = Package(name)

        return self.packages[name]

    def add_cell_bel_mapping(self, mapping):
        """
        Adds a new cell to BEL mapping
        """
        assert mapping.cell_type not in self.cell_bel_mappings, mapping.cell_type
        self.cell_bel_mappings[mapping.cell_type] = mapping

    def print_stats(self):
        """
        Prints out some statistics
        """
        print("site_types: {}".format(len(self.site_types)))
        print("tile_types: {}".format(len(self.tile_types)))
        print("tiles:      {}".format(len(self.tiles)))
        print("wires:      {}".format(len(self.wires)))
        print("nodes:      {}".format(len(self.nodes)))


# =============================================================================


class DeviceResourcesCapnp():
    def __init__(self, device, device_resources_schema,
                 logical_netlist_schema):
        self.device = device
        self.device_resources_schema = device_resources_schema
        self.logical_netlist_schema = logical_netlist_schema

        self.string_list = []
        self.string_map = {}

        self.site_type_map = {}
        self.site_pin_list = {}

        self.tile_type_map = {}
        self.tile_site_list = {}

    def populate_corner_model(self,
                              corner_model,
                              slow_min=None,
                              slow_typ=None,
                              slow_max=None,
                              fast_min=None,
                              fast_typ=None,
                              fast_max=None):
        fields = ['min', 'typ', 'max']
        slow = [slow_min, slow_typ, slow_max]
        fast = [fast_min, fast_typ, fast_max]
        if any(x is not None for x in slow):
            corner_model.slow.init("slow")
        if any(x is not None for x in fast):
            corner_model.fast.init("fast")
        for i, field in enumerate(fields):
            if slow[i] is not None:
                x = getattr(corner_model.slow.slow, field)
                setattr(x, field, slow[i])
        for i, field in enumerate(fields):
            if fast[i] is not None:
                x = getattr(corner_model.fast.fast, field)
                setattr(x, field, fast[i])

    def add_string_id(self, s):
        """
        Inserts a string to the global string list if not already there.
        Returns id of the string.
        """
        assert isinstance(s, str)

        if s in self.string_map:
            return self.string_map[s]

        self.string_map[s] = len(self.string_map)
        self.string_list.append(s)

        return self.string_map[s]

    def get_string_id(self, s):
        """
        Returns id of the string.
        """
        assert isinstance(s, str)
        assert s in self.string_map, s
        return self.string_map[s]

    def get_string(self, id):
        """
        Returns string for the given id
        """
        assert id < len(self.string_list), id
        return self.string_list[id]

    def build_string_index(self):
        """
        Index all strings
        """
        self.string_list = []
        self.string_map = {}

        # Index strings for site types
        for site_type in self.device.site_types.values():
            self.add_string_id(site_type.name)
            for site_pin in site_type.pins.values():
                self.add_string_id(site_pin.name)
            for bel in site_type.bels.values():
                self.add_string_id(bel.name)
                self.add_string_id(bel.type)
                for bel_pin in bel.pins.values():
                    self.add_string_id(bel_pin.name)
            for wire in site_type.wires.values():
                self.add_string_id(wire.name)

        # Index strings for tile types
        for tile_type in self.device.tile_types.values():
            self.add_string_id(tile_type.name)
            for wire in tile_type.wires:
                self.add_string_id(wire)

        # Index strings for tiles
        for tile in self.device.tiles.values():
            self.add_string_id(tile.name)
            for site in tile.sites.values():
                self.add_string_id(site.name)

        # Do not index wire strings. Those should refer to tile names and
        # wire in tile names. By not indexing them we allow write_wires() to
        # fail on a missing string which would indicate an error in the device
        # resources data.

        # Package names
        for package in self.device.packages.values():
            self.add_string_id(package.name)

            for pin in package.pins.values():
                self.add_string_id(pin.name)

        # Do not index package pin site and bel names. They should have been
        # already indexed during site processing

        # Cell names and their port names
        for library in self.device.cell_libraries.values():
            for cell in library.cells.values():
                self.add_string_id(cell.name)
                for port_name in cell.ports.keys():
                    self.add_string_id(port_name)

    def write_timings(self, device):
        self.node_timing_map = {}
        self.pip_timing_map = {}
        device.init("nodeTimings", len(self.device.node_delay_types))
        for i, node_timing in enumerate(self.device.node_delay_types.items()):
            key, value = node_timing
            self.node_timing_map[key] = i
            self.populate_corner_model(
                device.nodeTimings[i].resistance, slow_typ=value[0])
            self.populate_corner_model(
                device.nodeTimings[i].capacitance, slow_typ=value[1])
        device.init("pipTimings", len(self.device.pip_delay_types))
        for i, pip_timing in enumerate(self.device.pip_delay_types.items()):
            key, value = pip_timing
            self.pip_timing_map[key] = i
            self.populate_corner_model(
                device.pipTimings[i].inputCapacitance, slow_typ=value[0])
            self.populate_corner_model(
                device.pipTimings[i].internalCapacitance, slow_typ=value[1])
            self.populate_corner_model(
                device.pipTimings[i].internalDelay, slow_typ=value[2])
            self.populate_corner_model(
                device.pipTimings[i].outputResistance, slow_typ=value[3])
            self.populate_corner_model(
                device.pipTimings[i].outputCapacitance, slow_typ=value[4])

    def write_site_types(self, device):
        """
        Packs all SiteType objects and their children into the cap'n'proto
        schema.
        """
        self.site_type_map = {}
        self.site_pin_list = {}

        # Build site type list
        site_type_list = [s for s in self.device.site_types.values()]
        for i, site_type in enumerate(site_type_list):
            self.site_type_map[site_type.name] = i

        # Write each site type
        device.init("siteTypeList", len(site_type_list))
        for i, site_type in enumerate(site_type_list):
            site_type_capnp = device.siteTypeList[i]
            site_type_capnp.name = self.get_string_id(site_type.name)

            # Index all BELs and BEL pins
            bel_list = []
            bel_map = {}
            bel_pin_list = []
            bel_pin_map = {}

            for bel in site_type.bels.values():
                assert bel.name not in bel_map, bel.name
                bel_map[bel.name] = len(bel_list)
                bel_list.append(bel)

                for bel_pin in bel.pins.values():
                    key = (bel.name, bel_pin.name)
                    assert key not in bel_pin_map, key
                    bel_pin_map[key] = len(bel_pin_list)
                    bel_pin_list.append((bel, bel_pin))

            # Write BEL pins
            site_type_capnp.init("belPins", len(bel_pin_list))
            for i, (bel, bel_pin) in enumerate(bel_pin_list):
                bel_pin_capnp = site_type_capnp.belPins[i]
                bel_pin_capnp.name = self.get_string_id(bel_pin.name)
                bel_pin_capnp.dir = bel_pin.direction.value
                bel_pin_capnp.bel = bel_map[bel.name]

            # Write BELs
            site_type_capnp.init("bels", len(bel_list))
            for i, bel in enumerate(bel_list):
                bel_capnp = site_type_capnp.bels[i]
                bel_capnp.name = self.get_string_id(bel.name)
                bel_capnp.type = self.get_string_id(bel.type)
                bel_capnp.category = bel.category.value

                # Bel pin indices
                indices = [
                    bel_pin_map[(bel.name, pin.name)]
                    for pin in bel.pins.values()
                ]
                assert len(bel.pins) == len(indices)
                bel_capnp.init("pins", len(indices))
                for i, j in enumerate(indices):
                    bel_capnp.pins[i] = j

                # TODO: Inverting bels

            # Index and write site pins. Sort them so that input pins are
            # first.
            site_pins = sorted(
                site_type.pins.values(),
                key=lambda p: p.direction != Direction.Input)

            self.site_pin_list[site_type.name] = [p.name for p in site_pins]

            # Find index of the last input pin
            last_input = 0
            for i, pin in enumerate(site_pins):
                if pin.direction == Direction.Input:
                    last_input = i
            site_type_capnp.lastInput = last_input

            # Write site pins
            site_type_capnp.init("pins", len(site_pins))
            for i, pin in enumerate(site_pins):
                pin_capnp = site_type_capnp.pins[i]
                pin_capnp.name = self.get_string_id(pin.name)
                pin_capnp.dir = pin.direction.value

                # Get BEL pin
                bel = site_type.bels[pin.bel_name]
                bel_pin = next(iter(bel.pins.values()))

                pin_capnp.belpin = bel_pin_map[(bel.name, bel_pin.name)]

            # Write site wires
            site_wire_list = list(site_type.wires.values())
            site_type_capnp.init("siteWires", len(site_wire_list))
            for i, wire in enumerate(site_wire_list):
                site_wire_capnp = site_type_capnp.siteWires[i]
                site_wire_capnp.name = self.get_string_id(wire.name)

                # BEL pin indices
                site_wire_capnp.init("pins", len(wire.bel_pins))
                for j, (bel_name, bel_pin_name) in enumerate(wire.bel_pins):
                    bel = site_type.bels[bel_name]
                    bel_pin = bel.pins[bel_pin_name]
                    site_wire_capnp.pins[j] = bel_pin_map[(bel.name,
                                                           bel_pin.name)]

            # Write site PIPs
            site_type_capnp.init("sitePIPs", len(site_type.pips))
            for i, pip in enumerate(site_type.pips):
                site_pip_capnp = site_type_capnp.sitePIPs[i]

                bel = site_type.bels[pip.src_bel_pin[0]]
                bel_pin = bel.pins[pip.src_bel_pin[1]]
                site_pip_capnp.inpin = bel_pin_map[(bel.name, bel_pin.name)]

                bel = site_type.bels[pip.dst_bel_pin[0]]
                bel_pin = bel.pins[pip.dst_bel_pin[1]]
                site_pip_capnp.outpin = bel_pin_map[(bel.name, bel_pin.name)]

            # TODO: Alt site types

    def write_tile_types(self, device):
        """
        Packs all TileType objects and their children into the cap'n'proto
        schema.
        """
        self.tile_type_map = {}
        self.tile_site_list = {}

        # Build tile type list
        tile_type_list = [s for s in self.device.tile_types.values()]
        for i, tile_type in enumerate(tile_type_list):
            self.tile_type_map[tile_type.name] = i

        # Write each tile type
        device.init("tileTypeList", len(tile_type_list))
        for i, tile_type in enumerate(tile_type_list):
            tile_type_capnp = device.tileTypeList[i]
            tile_type_capnp.name = self.get_string_id(tile_type.name)

            # Build a list of tile wire string ids
            tile_wire_list = [self.get_string_id(w) for w in tile_type.wires]
            # Build a map of tile wires to their positions on the tile wire
            # list
            tile_wire_map = {
                self.get_string(w): i
                for i, w in enumerate(tile_wire_list)
            }

            # Tile wires
            tile_type_capnp.init("wires", len(tile_wire_list))
            for i, w in enumerate(tile_wire_list):
                tile_type_capnp.wires[i] = w

            # Tile PIPs
            tile_type_capnp.init("pips", len(tile_type.pips))
            for i, pip in enumerate(tile_type.pips):
                pip_capnp = tile_type_capnp.pips[i]
                pip_capnp.wire0 = tile_wire_map[pip.wire0]
                pip_capnp.wire1 = tile_wire_map[pip.wire1]
                pip_capnp.directional = pip.is_directional
                pip_capnp.buffered20 = pip.is_buffered20
                pip_capnp.buffered21 = pip.is_buffered21
                pip_capnp.timing = self.pip_timing_map[pip.delay_type]

                # TODO: Pseudo cells

            # Index site types
            site_type_list = list(tile_type.site_types.values())

            self.tile_site_list[tile_type.name] = [
                s.ref for s in site_type_list
            ]

            # Site type instances
            tile_type_capnp.init("siteTypes", len(site_type_list))
            for i, site_type in enumerate(site_type_list):
                site_type_capnp = tile_type_capnp.siteTypes[i]
                site_type_capnp.primaryType = self.site_type_map[site_type.
                                                                 type]

                # Site pins to tile wires map
                site_pin_list = self.site_pin_list[site_type.type]
                site_type_capnp.init("primaryPinsToTileWires",
                                     len(site_pin_list))
                for i, pin in enumerate(site_pin_list):
                    assert pin in site_type.primary_pins_to_tile_wires, "Unmapped site pin {}.{}".format(
                        site_type.type, pin)
                    wire_name = site_type.primary_pins_to_tile_wires[pin]
                    assert wire_name in tile_type.wires, wire_name
                    site_type_capnp.primaryPinsToTileWires[
                        i] = self.get_string_id(wire_name)

                # Alt site pins to primary site pins map
                # TODO:

            # Constant sources
            tile_type_capnp.init("constants", len(tile_type.constants))
            for i, (constant, wires) in enumerate(tile_type.constants.items()):
                constants_capnp = tile_type_capnp.constants[i]
                constants_capnp.constant = constant.value

                constants_capnp.init("wires", len(wires))
                for j, wire in enumerate(wires):
                    constants_capnp.wires[j] = tile_wire_map[wire]

    def write_tiles(self, device):
        """
        Packs all Tile objects and their children into the cap'n'proto
        schema.
        """

        # Build tile list
        tile_list = [t for t in self.device.tiles.values()]

        # Write each tile
        device.init("tileList", len(tile_list))
        for i, tile in enumerate(tile_list):
            tile_capnp = device.tileList[i]
            tile_capnp.name = self.get_string_id(tile.name)
            tile_capnp.type = self.tile_type_map[tile.type]
            tile_capnp.col = tile.loc[0]
            tile_capnp.row = tile.loc[1]

            # Get the site list of the tile type
            tile_site_list = self.tile_site_list[tile.type]
            assert len(tile_site_list) == len(tile.sites)

            # Write sites
            tile_capnp.init("sites", len(tile_site_list))
            for j, ref in enumerate(tile_site_list):
                site = tile.sites[ref]
                site_capnp = tile_capnp.sites[j]
                site_capnp.name = self.get_string_id(site.name)
                site_capnp.type = j

    def write_wires(self, device):
        """
        Packs all wire objects to the cap'n'proto schema
        """

        device.init("wires", len(self.device.wires))
        for i, _ in enumerate(self.device.wires):
            wire_capnp = device.wires[i]

            # Get string literals and map them with the cap'n'p string map
            wire = self.device.get_wire(i)
            wire_capnp.tile = self.get_string_id(wire.tile)
            wire_capnp.wire = self.get_string_id(wire.wire)

    def write_nodes(self, device):
        """
        Packs all node objects to the cap'n'proto schema
        """

        device.init("nodes", len(self.device.nodes))
        for i, node in enumerate(self.device.nodes):
            node_capnp = device.nodes[i]
            node_capnp.init("wires", len(node[0]))
            for j, wire_id in enumerate(node[0]):
                wire = self.device.get_wire(wire_id)
                node_capnp.wires[j] = wire_id
            node_capnp.nodeTiming = self.node_timing_map[node[1]]

    def write_packages(self, device):
        """
        Encodes device package data
        """

        device.init("packages", len(self.device.packages))
        for i, package in enumerate(self.device.packages.values()):
            package_capnp = device.packages[i]
            package_capnp.name = self.get_string_id(package.name)

            package_capnp.init("packagePins", len(package.pins))
            for j, pin in enumerate(package.pins.values()):
                pin_capnp = package_capnp.packagePins[j]

                assert pin.site_name in self.device.sites_by_name, pin.site_name
                site_id = self.device.sites_by_name[pin.site_name]
                site = self.device.sites[site_id]

                site_type = self.device.site_types[site.type]
                assert pin.bel_name in site_type.bels, pin.bel_name
                bel = site_type.bels[pin.bel_name]

                pin_capnp.packagePin = self.get_string_id(pin.name)
                pin_capnp.site.site = self.get_string_id(site.name)
                pin_capnp.bel.bel = self.get_string_id(bel.name)

    def write_constants(self, device):
        """
        Packs all constant sources/bels objects to the cap'n'proto schema
        """

        device.constants.defaultBestConstant = "noPreference"
        device.constants.init("siteSources", len(self.device.constants))
        for i, (key, const) in enumerate(self.device.constants.items()):
            device.constants.siteSources[i].siteType = self.get_string_id(
                key[0])
            device.constants.siteSources[i].bel = self.get_string_id(key[1])
            device.constants.siteSources[i].belPin = self.get_string_id(key[2])
            device.constants.siteSources[
                i].constant = "vcc" if const == "VCC" else "gnd"
        device.constants.gndCellType = self.get_string_id("GND")
        device.constants.gndCellPin = self.get_string_id("G")
        device.constants.vccCellType = self.get_string_id("VCC")
        device.constants.vccCellPin = self.get_string_id("V")

    def write_cell_bel_mappings(self, device):
        """
        Packs all cell <-> bel mapping objects to the cap'n'proto schema
        """

        # Make a cell-bel mapping list
        cell_bel_mappings = list(self.device.cell_bel_mappings.values())

        # Write each one
        device.init("cellBelMap", len(cell_bel_mappings))
        for i, cell_bel_mapping in enumerate(cell_bel_mappings):
            cell_bel_mapping_capnp = device.cellBelMap[i]
            cell_bel_mapping_capnp.cell = self.get_string_id(
                cell_bel_mapping.cell_type)

            # TODO: Parameter-dependent mapping

            # Rearrange entries so that they can be encoded according to the
            # schema.
            entries = {}
            for entry in cell_bel_mapping.entries:
                key = tuple(entry.pin_map.items())

                if key not in entries:
                    entries[key] = {}
                if entry.site_type not in entries[key]:
                    entries[key][entry.site_type] = []

                entries[key][entry.site_type].append(entry.bel)

            # Encode
            cell_bel_mapping_capnp.init("commonPins", len(entries))
            for j, (pin_map, bels_by_site_type) in enumerate(entries.items()):
                common_pins_capnp = cell_bel_mapping_capnp.commonPins[j]

                # Pin map
                common_pins_capnp.init("pins", len(pin_map))
                for k, (cell_pin, bel_pin) in enumerate(pin_map):
                    common_pins_capnp.pins[k].cellPin = self.get_string_id(
                        cell_pin)
                    common_pins_capnp.pins[k].belPin = self.get_string_id(
                        bel_pin)

                # Site types an bels
                common_pins_capnp.init("siteTypes", len(bels_by_site_type))
                for k, (site_type,
                        bels) in enumerate(bels_by_site_type.items()):
                    site_type_bel_entry_capnp = common_pins_capnp.siteTypes[k]
                    site_type_bel_entry_capnp.siteType = self.get_string_id(
                        site_type)

                    site_type_bel_entry_capnp.init("bels", len(bels))
                    for m, bel in enumerate(bels):
                        site_type_bel_entry_capnp.bels[m] = self.get_string_id(
                            bel)

            cell_bel_mapping_capnp.init("pinsDelay",
                                        len(cell_bel_mapping.delay_mapping))
            for k, delay in enumerate(cell_bel_mapping.delay_mapping):
                pin_delay = cell_bel_mapping_capnp.pinsDelay[k]
                pin_delay.pinsDelayType = delay[3]
                self.populate_corner_model(pin_delay.cornerModel, *delay[2])
                if isinstance(delay[0], tuple):
                    pin_delay.firstPin.pin = self.get_string_id(delay[0][0])
                    pin_delay.firstPin.clockEdge = delay[0][1]
                else:
                    pin_delay.firstPin.pin = self.get_string_id(delay[0])
                if isinstance(delay[1], tuple):
                    pin_delay.secondPin.pin = self.get_string_id(delay[1][0])
                    pin_delay.secondPin.clockEdge = delay[1][1]
                else:
                    pin_delay.secondPin.pin = self.get_string_id(delay[1])

    def to_capnp(self):
        """
        Encodes stuff into a cap'n'proto message.
        """

        # Initialize the message
        device = self.device_resources_schema.Device.new_message()
        device.name = self.device.name

        # Strings
        self.build_string_index()

        device.init("strList", len(self.string_list))
        for i, s in enumerate(self.string_list):
            device.strList[i] = s

        # Node and PIP timings
        self.write_timings(device)

        # Site types
        self.write_site_types(device)
        # Tile types
        self.write_tile_types(device)
        # Tiles
        self.write_tiles(device)
        # Wires
        self.write_wires(device)
        # Nodes
        self.write_nodes(device)
        # Device packages
        self.write_packages(device)
        # Constants
        self.write_constants(device)

        # Cell <-> BEL mappings
        self.write_cell_bel_mappings(device)

        # Logical netlist containing primitives and macros
        device.primLibs = output_logical_netlist(
            logical_netlist_schema=self.logical_netlist_schema,
            libraries=self.device.cell_libraries,
            name="Testarch_primitives",
            top_instance_name=None,
            top_instance=None,
        )

        # Fix names, as logical network should use string IDs from global string table, see issue #47
        for port in device.primLibs.portList:
            port.name = self.get_string_id(device.primLibs.strList[port.name])
        for cell in device.primLibs.cellDecls:
            cell.name = self.get_string_id(device.primLibs.strList[cell.name])
        device.primLibs.strList = []

        return device
