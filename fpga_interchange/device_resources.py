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

from collections import namedtuple
from .logical_netlist import Direction


def first_upper(s):
    """ Convert first letter in string. """
    return s[0].upper() + s[1:]


def convert_direction(s):
    """ Convert capnp enum to logical_netlist.Direction. """
    return Direction[first_upper(str(s))]


def can_connect_via_site_wire(a_site, a_site_wire, b_site, b_site_wire):
    """ Are these two site wires the same connection resource? """
    if a_site != b_site:
        # Not in same site, not connected
        return False

    # Must be connected via the same site wire
    return a_site_wire == b_site_wire


def can_be_connected(a_direction, b_direction):
    """ Can two resources with the following directions be connected? """
    if a_direction == Direction.Inout or b_direction == Direction.Inout:
        return True
    elif a_direction == Direction.Input:
        return b_direction == Direction.Output
    else:
        assert a_direction == Direction.Output, (a_direction, b_direction)
        return b_direction == Direction.Input, (a_direction, b_direction)


class Tile(namedtuple('Tile', 'tile_index tile_name_index tile_type_index')):
    pass


class Site(
        namedtuple(
            'Site',
            'tile_index tile_name_index site_index tile_type_site_type_index site_type_index alt_index'
        )):
    pass


class SiteWire(
        namedtuple('SiteWire', 'tile_index site_index site_wire_index')):
    pass


class SitePinNames(
        namedtuple('SitePinNames',
                   'tile_name site_name site_type_name pin_name wire_name')):
    pass


class Node(namedtuple('Node', 'node_index')):
    """ Node is a lightweight class to wrap the node index.

    This class may be replaced with a more complicated object when/if node
    folding is supported.

    Must implement __eq__ and __hash__

    """


class BelPin():
    """ BEL Pin device resource object. """

    def __init__(self, site, bel_pin_index, site_wire_index, direction,
                 is_site_pin):
        self.site = site
        self.site_wire_index = site_wire_index
        self.bel_pin_index = bel_pin_index
        self.direction = direction
        self.is_site_pin = is_site_pin

    def __repr__(self):
        return "BelPin({}, {}, {}, {}, {})".format(
            repr(self.site), repr(self.bel_pin_index),
            repr(self.site_wire_index), repr(self.direction),
            repr(self.is_site_pin))

    def site_wires(self):
        """ Return site wires that this object is attached too. """
        if self.site_wire_index is not None:
            return [
                SiteWire(self.site.tile_index, self.site.site_index,
                         self.site_wire_index)
            ]
        else:
            return []

    def nodes(self):
        """ Return site wires that this object is attached too. """
        return []

    def is_connected(self, other_object):
        """ Return true if this object and other_object are directly connected. """
        # BelPin's for the site pins have a direct relationship.
        if other_object.is_site_pin_for(self.site, self.bel_pin_index):
            return True
        # Otherwire Bel Pins are connected via site wires to other Bel Pins
        elif other_object.can_connect_via_site_wire(
                self.site, self.site_wire_index, self.direction):
            return True
        else:
            return False

    def is_site_pin_for(self, site, bel_pin_index):
        """ Return true if this object is the site pin for the specified BEL pin. """
        # BEL pins are not site pins for other BEL pins.
        return False

    def can_connect_via_site_wire(self, other_site, other_site_wire_index,
                                  other_direction):
        """ Return true if this object can connected to the specified site wire. """
        if not can_connect_via_site_wire(self.site, self.site_wire_index,
                                         other_site, other_site_wire_index):
            # Not connected at all
            return False

        return can_be_connected(self.direction, other_direction)

    def is_bel_pin(self, site, bel_pin_index):
        """ Returns true if this object is the specified BEL pin. """
        return self.site == site and self.bel_pin_index == bel_pin_index

    def is_node_connected(self, node):
        """ Returns true if this object is connected to the specified node. """
        return False

    def is_root(self):
        """ Returns true if this object could be a net root. """
        return self.direction in [Direction.Output, Direction.Inout
                                  ] and not self.is_site_pin

    def root_priority(self):
        """ What root priority does this BEL pin have?

        Lower priority take precedence over high priority.

        In cases where a site wire has multiple possible roots, think an IOBUF
        which will have a Pad with Inout and a OUTBUF with Output, the Output
        take precedence.

        """
        if self.direction == Direction.Output:
            return 0
        elif self.direction == Direction.Inout:
            return 1
        else:
            assert False, self.direction


class SitePin():
    """ Site pin device resource object. """

    def __init__(self, site, site_pin_index, bel_pin_index, site_wire_index,
                 node, direction):
        self.site = site
        self.site_pin_index = site_pin_index
        self.bel_pin_index = bel_pin_index
        self.site_wire_index = site_wire_index
        self.node = node
        self.direction = direction

    def __repr__(self):
        return "SitePin({}, {}, {}, {}, {}, {})".format(
            repr(self.site), repr(self.site_pin_index),
            repr(self.bel_pin_index), repr(self.site_wire_index),
            repr(self.node), repr(self.direction))

    def site_wires(self):
        """ Return site wires that this object is attached too. """
        return [
            SiteWire(self.site.tile_index, self.site.site_index,
                     self.site_wire_index)
        ]

    def nodes(self):
        """ Return site wires that this object is attached too. """
        return [self.node]

    def is_connected(self, other_object):
        """ Return true if this object and other_object are directly connected. """
        if other_object.is_bel_pin(self.site, self.bel_pin_index):
            return True
        else:
            return other_object.is_node_connected(self.node)

    def is_site_pin_for(self, site, bel_pin_index):
        """ Return true if this object is the site pin for the specified BEL pin. """
        return self.site == site and self.bel_pin_index == bel_pin_index

    def can_connect_via_site_wire(self, other_site_index,
                                  other_site_wire_index, other_direction):
        """ Return true if this object can connected to the specified site wire. """
        return False

    def is_bel_pin(self, site, bel_pin_index):
        """ Returns true if this object is the specified BEL pin. """
        return False

    def is_node_connected(self, node):
        """ Returns true if this object is connected to the specified node. """
        return self.node == node

    def is_root(self):
        """ Returns true if this object could be a net root. """
        return False


class SitePip():
    """ Site pip device resource object. """

    def __init__(self, site, in_bel_pin_index, out_bel_pin_index,
                 in_site_wire_index, out_site_wire_index):
        self.site = site
        self.in_bel_pin_index = in_bel_pin_index
        self.out_bel_pin_index = out_bel_pin_index
        self.in_site_wire_index = in_site_wire_index
        self.out_site_wire_index = out_site_wire_index

    def __repr__(self):
        return "SitePip({}, {}, {}, {}, {})".format(
            repr(self.site), repr(self.in_bel_pin_index),
            repr(self.out_bel_pin_index), repr(self.in_site_wire_index),
            repr(self.out_site_wire_index))

    def site_wires(self):
        """ Return site wires that this object is attached too. """
        return [
            SiteWire(self.site.tile_index, self.site.site_index,
                     self.in_site_wire_index),
            SiteWire(self.site.tile_index, self.site.site_index,
                     self.out_site_wire_index),
        ]

    def nodes(self):
        """ Return site wires that this object is attached too. """
        return []

    def is_connected(self, other_object):
        """ Return true if this object and other_object are directly connected. """
        if other_object.can_connect_via_site_wire(
                self.site, self.in_site_wire_index, Direction.Input):
            return True
        else:
            return other_object.can_connect_via_site_wire(
                self.site, self.out_site_wire_index, Direction.Output)

    def is_site_pin_for(self, site, bel_pin_index):
        """ Return true if this object is the site pin for the specified BEL pin. """
        return False

    def can_connect_via_site_wire(self, other_site, other_site_wire_index,
                                  other_direction):
        """ Return true if this object can connected to the specified site wire. """
        if can_connect_via_site_wire(self.site, self.in_site_wire_index,
                                     other_site, other_site_wire_index):
            return can_be_connected(Direction.Input, other_direction)
        elif can_connect_via_site_wire(self.site, self.out_site_wire_index,
                                       other_site, other_site_wire_index):
            return can_be_connected(Direction.Output, other_direction)
        else:
            return False

    def is_bel_pin(self, site, bel_pin_index):
        """ Returns true if this object is the specified BEL pin. """
        if not self.site == site:
            return False
        else:
            return bel_pin_index in (self.in_bel_pin_index,
                                     self.out_bel_pin_index)

    def is_node_connected(self, node):
        """ Returns true if this object is connected to the specified node. """
        return False

    def is_root(self):
        """ Returns true if this object could be a net root. """
        return False


class Pip():
    """ Pip device resource object. """

    def __init__(self, node0, node1, directional):
        self.node0 = node0
        self.node1 = node1
        self.directional = directional

    def __repr__(self):
        return "Pip({}, {}, {})".format(
            repr(self.node0), repr(self.node1), repr(self.directional))

    def site_wires(self):
        """ Return site wires that this object is attached too. """
        return []

    def nodes(self):
        """ Return site wires that this object is attached too. """
        return [self.node0, self.node1]

    def is_connected(self, other_object):
        """ Return true if this object and other_object are directly connected. """
        if other_object.is_node_connected(self.node0):
            return True
        else:
            return other_object.is_node_connected(self.node1)

    def is_site_pin_for(self, site, bel_pin_index):
        """ Return true if this object is the site pin for the specified BEL pin. """
        return False

    def can_connect_via_site_wire(self, other_site_index,
                                  other_site_wire_index, other_direction):
        """ Return true if this object can connected to the specified site wire. """
        return False

    def is_bel_pin(self, site, bel_pin_index):
        """ Returns true if this object is the specified BEL pin. """
        return False

    def is_node_connected(self, node):
        """ Returns true if this object is connected to the specified node. """
        return node in [self.node0, self.node1]

    def is_root(self):
        """ Returns true if this object could be a net root. """
        return False


class SiteType():
    """ Object for looking up device resources from a site type.

    Do not construct or use directly.  Instead use DeviceResources.

    """

    def __init__(self, strs, site_type, site_type_index):
        self.site_type = strs[site_type.name]
        self.site_type_index = site_type_index

        bel_pin_index_to_site_wire_index = {}
        for site_wire_index, site_wire in enumerate(site_type.siteWires):
            for bel_pin_index in site_wire.pins:
                bel_pin_index_to_site_wire_index[
                    bel_pin_index] = site_wire_index

        self.bel_pins = {}
        for bel_pin_index, bel_pin in enumerate(site_type.belPins):
            bel_name = strs[bel_pin.bel]
            bel_pin_name = strs[bel_pin.name]
            direction = convert_direction(bel_pin.dir)
            if bel_pin_index in bel_pin_index_to_site_wire_index:
                site_wire_index = bel_pin_index_to_site_wire_index[
                    bel_pin_index]
            else:
                site_wire_index = None

            key = (bel_name, bel_pin_name)
            assert key not in self.bel_pins
            self.bel_pins[key] = bel_pin_index, site_wire_index, direction

        self.bel_pin_to_site_pins = {}
        self.site_pins = {}
        for site_pin_index, site_pin in enumerate(site_type.pins):
            site_pin_name = strs[site_pin.name]
            assert site_pin_name not in self.site_pins
            bel_pin_index = site_pin.belpin

            assert bel_pin_index not in self.bel_pin_to_site_pins
            self.bel_pin_to_site_pins[bel_pin_index] = site_pin_index

            if bel_pin_index in bel_pin_index_to_site_wire_index:
                site_wire_index = bel_pin_index_to_site_wire_index[
                    bel_pin_index]
            else:
                site_wire_index = None

            self.site_pins[site_pin_name] = (site_pin_index, bel_pin_index,
                                             site_wire_index,
                                             convert_direction(site_pin.dir))

        self.site_pips = {}
        for site_pip in site_type.sitePIPs:
            out_bel_pin = site_type.belPins[site_pip.outpin]
            self.site_pips[site_pip.inpin] = strs[out_bel_pin.name]

    def bel_pin(self, site, bel, pin):
        """ Return BelPin device resource for BEL pin in site.

        site (Site) - Site tuple
        bel (str) - BEL name
        pin (str) - BEL pin name

        """
        assert site.site_type_index == self.site_type_index
        bel_pin_index, site_wire_index, direction = self.bel_pins[bel, pin]

        return BelPin(
            site=site,
            bel_pin_index=bel_pin_index,
            site_wire_index=site_wire_index,
            direction=direction,
            is_site_pin=bel_pin_index in self.bel_pin_to_site_pins,
        )

    def site_pin(self, site, device_resources, pin):
        """ Return SitePin device resource for site pin in site.

        site (Site) - Site tuple
        pin (str) - Site pin name

        """
        assert site.site_type_index == self.site_type_index

        assert pin in self.site_pins, (self.site_type, pin,
                                       self.site_pins.keys())
        site_pin_index, bel_pin_index, site_wire_index, direction = self.site_pins[
            pin]

        site_pin_names = device_resources.get_site_pin(site, site_pin_index)
        assert self.site_type == site_pin_names.site_type_name, (
            self.site_type, site_pin_names)
        assert pin == site_pin_names.pin_name, (pin, site_pin_names)

        node = device_resources.node(
            device_resources.strs[site.tile_name_index],
            site_pin_names.wire_name,
        )

        return SitePin(
            site=site,
            site_pin_index=site_pin_index,
            bel_pin_index=bel_pin_index,
            site_wire_index=site_wire_index,
            node=node,
            direction=direction)

    def site_pip(self, site, bel, pin):
        """ Return SitePip device resource for site PIP in site.

        site (Site) - Site tuple
        bel (str) - BEL name containing site PIP.
        pin (str) - BEL pin name for specific edge.

        """
        assert site.site_type_index == self.site_type_index

        key = bel, pin
        in_bel_pin_index, in_site_wire_index, direction = self.bel_pins[key]
        assert direction == Direction.Input, (
            site,
            bel,
            pin,
            direction,
        )

        out_pin = self.site_pips[in_bel_pin_index]
        out_bel_pin_index, out_site_wire_index, direction = self.bel_pins[
            bel, out_pin]
        assert direction == Direction.Output

        return SitePip(
            site=site,
            in_bel_pin_index=in_bel_pin_index,
            out_bel_pin_index=out_bel_pin_index,
            in_site_wire_index=in_site_wire_index,
            out_site_wire_index=out_site_wire_index)


GenericPip = namedtuple('GenericPip', 'wire0 wire1 directional')


class TileType():
    """ Object for looking up device resources from a tile type.

    Do not construct or use directly.  Instead use DeviceResources.

    """

    def __init__(self, strs, tile_type, tile_type_index):
        self.tile_type_index = tile_type_index

        self.string_index_to_wire_id_in_tile_type = {}
        for wire_id, string_index in enumerate(tile_type.wires):
            self.string_index_to_wire_id_in_tile_type[string_index] = wire_id

        self.pips = []
        self.wire_id_to_pip = {}
        for pip_idx, pip in enumerate(tile_type.pips):
            self.pips.append(GenericPip(pip.wire0, pip.wire1, pip.directional))

            self.wire_id_to_pip[pip.wire0, pip.wire1] = pip
            if not pip.directional:
                self.wire_id_to_pip[pip.wire1, pip.wire0] = pip

    def pip(self, wire0, wire1):
        """ Return GenericPip for specified PIP in tile type.

        wire0 (int) - StringIdx for wire0 name
        wire1 (int) - StringIdx for wire1 name

        """
        wire_id0 = self.string_index_to_wire_id_in_tile_type[wire0]
        wire_id1 = self.string_index_to_wire_id_in_tile_type[wire1]
        return self.wire_id_to_pip[wire_id0, wire_id1]


class DeviceResources():
    """ Object for getting specific a device resource from DeviceResources capnp. """

    def __init__(self, device_resource_capnp):
        self.device_resource_capnp = device_resource_capnp
        self.strs = [s for s in self.device_resource_capnp.strList]

        self.string_index = {}
        for idx, s in enumerate(self.strs):
            self.string_index[s] = idx

        self.site_types = {}
        self.tile_types = {}

        self.tile_type_to_idx = {}
        for tile_type_idx, tile_type in enumerate(
                self.device_resource_capnp.tileTypeList):
            self.tile_type_to_idx[tile_type.name] = tile_type_idx

        self.site_type_names = []
        self.site_type_name_to_index = {}
        for site_type_index, site_type in enumerate(
                self.device_resource_capnp.siteTypeList):
            site_type_name = self.strs[site_type.name]
            assert site_type_name not in self.site_type_name_to_index
            self.site_type_names.append(site_type_name)
            self.site_type_name_to_index[site_type_name] = site_type_index

        self.tile_name_to_tile = {}
        self.site_name_to_site = {}
        for tile_idx, tile in enumerate(self.device_resource_capnp.tileList):
            tile_name = self.strs[tile.name]
            tile_name_index = self.string_index[tile_name]
            assert tile_name not in self.tile_name_to_tile
            tile_type_index = self.tile_type_to_idx[tile.type]
            self.tile_name_to_tile[tile_name] = Tile(
                tile_index=tile_idx,
                tile_name_index=tile_name_index,
                tile_type_index=tile_type_index)

            for site_idx, site in enumerate(tile.sites):
                site_name = self.strs[site.name]
                assert site_name not in self.site_name_to_site, site_name
                self.site_name_to_site[site_name] = {}

                tile_type_site_type_index = site.type
                site_type_index = self.device_resource_capnp.tileTypeList[
                    tile_type_index].siteTypes[site.type].primaryType

                site_type_name = self.site_type_names[site_type_index]
                self.site_name_to_site[site_name][site_type_name] = Site(
                    tile_index=tile_idx,
                    tile_name_index=tile_name_index,
                    site_index=site_idx,
                    tile_type_site_type_index=tile_type_site_type_index,
                    site_type_index=site_type_index,
                    alt_index=None)

                for alt_index, alt_site_type_index in enumerate(
                        self.device_resource_capnp.
                        siteTypeList[site_type_index].altSiteTypes):
                    site_type_name = self.site_type_names[alt_site_type_index]
                    self.site_name_to_site[site_name][site_type_name] = Site(
                        tile_index=tile_idx,
                        tile_name_index=tile_name_index,
                        site_index=site_idx,
                        tile_type_site_type_index=tile_type_site_type_index,
                        site_type_index=alt_site_type_index,
                        alt_index=alt_index)

        self.tile_wire_index_to_node_index = None

    def build_node_index(self):
        """ Build node index for looking up wires to nodes. """
        self.tile_wire_index_to_node_index = {}
        for node_idx, node in enumerate(self.device_resource_capnp.nodes):
            for wire_idx in node.wires:
                wire = self.device_resource_capnp.wires[wire_idx]
                key = wire.tile, wire.wire
                self.tile_wire_index_to_node_index[key] = node_idx

    def get_site_type(self, site_type_index):
        """ Get SiteType object for specified site type index. """
        if site_type_index not in self.site_types:
            self.site_types[site_type_index] = SiteType(
                self.strs,
                self.device_resource_capnp.siteTypeList[site_type_index],
                site_type_index)

        return self.site_types[site_type_index]

    def get_tile_type(self, tile_type_index):
        """ Get TileType object for specified tile type index. """
        if tile_type_index not in self.tile_types:
            num_tile_types = len(self.device_resource_capnp.tileTypeList)
            assert tile_type_index < num_tile_types, (tile_type_index,
                                                      num_tile_types)
            self.tile_types[tile_type_index] = TileType(
                self.strs,
                self.device_resource_capnp.tileTypeList[tile_type_index],
                tile_type_index)

        return self.tile_types[tile_type_index]

    def bel_pin(self, site_name, site_type, bel, pin):
        """ Return BelPin device resource for BEL pin in site.

        site_name (str) - Name of site
        site_type (str) - Name of specific site type being queried.
        bel (str) - BEL name containing site PIP.
        pin (str) - BEL pin name for specific edge.

        """
        site = self.site_name_to_site[site_name][site_type]
        return self.get_site_type(site.site_type_index).bel_pin(site, bel, pin)

    def site_pin(self, site_name, site_type, pin):
        """ Return SitePin device resource for site pin in site.

        site_name (str) - Name of site
        site_type (str) - Name of specific site type being queried.
        pin (str) - Site pin name

        """
        site = self.site_name_to_site[site_name][site_type]
        return self.get_site_type(site.site_type_index).site_pin(
            site, self, pin)

    def site_pip(self, site_name, site_type, bel, pin):
        """ Return SitePip device resource for site PIP in site.

        site_name (str) - Name of site
        site_type (str) - Name of specific site type being queried.
        bel (str) - BEL name containing site PIP.
        pin (str) - BEL pin name for specific edge.

        """
        site = self.site_name_to_site[site_name][site_type]
        return self.get_site_type(site.site_type_index).site_pip(
            site, bel, pin)

    def pip(self, tile_name, wire0, wire1):
        """ Return Pip device resource for pip in tile.

        tile_name (str) - Name of tile
        wire0 (str) - wire0 name
        wire1 (str) - wire1 name

        """
        tile = self.tile_name_to_tile[tile_name]
        tile_type = self.get_tile_type(tile.tile_type_index)

        wire0_index = self.string_index[wire0]
        wire1_index = self.string_index[wire1]
        generic_pip = tile_type.pip(wire0_index, wire1_index)

        return Pip(
            node0=self.node(tile_name, wire0),
            node1=self.node(tile_name, wire1),
            directional=generic_pip.directional)

    def node(self, tile_name, wire_name):
        """ Return Node object for specified wire.

        tile_name (str) - Name of tile
        wire_name (str) - Name of wire in tile.

        """
        assert tile_name in self.string_index, tile_name
        assert wire_name in self.string_index, wire_name

        tile_name_index = self.string_index[tile_name]
        wire_name_index = self.string_index[wire_name]

        if self.tile_wire_index_to_node_index is None:
            self.build_node_index()

        key = tile_name_index, wire_name_index
        assert key in self.tile_wire_index_to_node_index, (
            self.strs[tile_name_index],
            self.strs[wire_name_index],
        )

        node_index = self.tile_wire_index_to_node_index[key]
        return Node(node_index=node_index)

    def get_site_pin(self, site, site_pin_index):
        """ Get SitePinNames for specified site pin.

        site (Site) - Site tuple
        site_pin_index (int) - Index into SiteType.pins list.

        Site pin to tile relationships are estabilished through the site type
        in tile type data.

        If the site tuple indicates this is a primary site type, then the
        tile wire can be returned directly.

        If the site tuple indicates this is an alternate site type, then the
        tile wire is found by first mapping the site pin from the alternate
        site type to the primary site type.  At that point, the tile wire can
        be found.

        """
        tile = self.device_resource_capnp.tileList[site.tile_index]
        tile_type_index = self.tile_type_to_idx[tile.type]
        tile_type = self.device_resource_capnp.tileTypeList[tile_type_index]
        site_type_in_tile_type = tile_type.siteTypes[site.
                                                     tile_type_site_type_index]
        if site.alt_index is None:
            # This site type is the primary site type, return the tile wire
            # directly.
            site_type = self.device_resource_capnp.siteTypeList[
                site_type_in_tile_type.primaryType]
            site_type_name = self.strs[site_type.name]
            pin_name = self.strs[site_type.pins[site_pin_index].name]
            wire_name = self.strs[site_type_in_tile_type.
                                  primaryPinsToTileWires[site_pin_index]]
        else:
            # This site type is an alternate site type.
            prim_site_type = self.device_resource_capnp.siteTypeList[
                site_type_in_tile_type.primaryType]
            site_type = self.device_resource_capnp.siteTypeList[
                prim_site_type.altSiteTypes[site.alt_index]]
            site_type_name = self.strs[site_type.name]
            pin_name = self.strs[site_type.pins[site_pin_index].name]

            # First translate the site_pin_index from the alternate site type
            # To the primary site type pin index.
            prim_site_pin_index = site_type_in_tile_type.altPinsToPrimaryPins[
                site.alt_index].pins[site_pin_index]
            # Then lookup the tile wire using the primary site pin index.
            wire_name = self.strs[site_type_in_tile_type.
                                  primaryPinsToTileWires[prim_site_pin_index]]

        return SitePinNames(
            tile_name=self.strs[tile.name],
            site_name=self.strs[tile.sites[site.site_index].name],
            site_type_name=site_type_name,
            pin_name=pin_name,
            wire_name=wire_name)
