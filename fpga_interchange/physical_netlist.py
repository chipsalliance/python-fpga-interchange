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
""" Classes for representing and creating a physical netlist in python,
along with reading and writing the physical netlist format.

Useful starting points:

  PhysicalNetlist - class that can read and write physical netlist format,
                    and be constructed and inspected from Python.

"""

import enum
from collections import namedtuple
from .route_stitching import RoutingTree, stitch_segments, flatten_segments


# Physical cell type enum.
class PhysicalCellType(enum.Enum):
    Locked = 0
    Port = 1
    Gnd = 2
    Vcc = 3


class PhysicalNetType(enum.Enum):
    # Net is just a signal, not a VCC or GND tied net.
    Signal = 0
    # Net is tied to GND.
    Gnd = 1
    # Net is tied to VCC.
    Vcc = 2


# Represents an active pip between two tile wires.
#
# tile (str) - Name of tile
# wire0 (str) - Name of upstream wire to pip
# wire1 (str) - Name of downstream wire from pip
# forward (bool) - For bidirectional pips, is the connection from wire0 to
#                  wire1 (forward=True) or wire1 to wire0 (forward=False).
Pip = namedtuple('Pip', 'tile wire0 wire1 forward')

# Pin placement directive
#
# Associates a BEL pin with a Cell pin
#
# bel_pin (str) - Name of BEL pin being associated
# cell_pin (str) - Name of Cell pin being associated
# bel (str) - Name of BEL that contains BEL pin. If None is BEL from Placement
#             class.
# other_cell_type (str) - Used to define multi cell mappings.
# other_cell_name (str) - Used to define multi cell mappings.
Pin = namedtuple('Pin', 'bel_pin cell_pin bel other_cell_type other_cell_name')

PhysicalNet = namedtuple('PhysicalNet', 'name type sources stubs')


class Placement():
    """ Class for defining a Cell placement within a design.

    cell_type (str) - Type of cell being placed
    cell_name (str) - Name of cell instance being placed.
    site (str) - Site Cell is being placed within.
    bel (str) - Name of primary BEL being placed.

    """

    def __init__(self, cell_type, cell_name, site, bel):
        self.cell_type = cell_type
        self.cell_name = cell_name

        self.site = site
        self.bel = bel

        self.pins = []
        self.other_bels = set()

    def add_bel_pin_to_cell_pin(self,
                                bel_pin,
                                cell_pin,
                                bel=None,
                                other_cell_type=None,
                                other_cell_name=None):
        """ Add a BEL pin -> Cell pin association.

        bel_pin (str) - Name of BEL pin being associated.
        cell_pin (str) - NAme of Cell pin being associated.

        """
        if bel is None:
            bel = self.bel
        elif bel != self.bel:
            self.other_bels.add(bel)

        self.pins.append(
            Pin(
                bel_pin=bel_pin,
                cell_pin=cell_pin,
                bel=bel,
                other_cell_type=other_cell_type,
                other_cell_name=other_cell_name,
            ))


def descend_branch(obj, node, string_id):
    """ Descend a branch to continue outputting the interchange to capnp object. """
    obj.init('branches', len(node.branches))

    for branch_obj, branch in zip(obj.branches, node.branches):
        branch.output_interchange(branch_obj, string_id)


class PhysicalBelPin():
    """ Python class that represents a BEL pin in a physical net.

    site (str) - Site containing BEL pin
    bel (str) - BEL containing BEL pin
    pin (str) - BEL pin in physical net.
    direction (Direction) - Direction of BEL pin.

    """

    def __init__(self, site, bel, pin):
        self.site = site
        self.bel = bel
        self.pin = pin

        self.branches = []

    def output_interchange(self, obj, string_id):
        """ Output this route segment and all branches beneth it.

        obj (physical_netlist.RouteBranch pycapnp object) -
            Object to write PhysicalBelPin into
        string_id (str -> int) - Function to intern strings into PhysNetlist
                                 string list.

        """
        obj.routeSegment.init('belPin')
        obj.routeSegment.belPin.site = string_id(self.site)
        obj.routeSegment.belPin.bel = string_id(self.bel)
        obj.routeSegment.belPin.pin = string_id(self.pin)

        descend_branch(obj, self, string_id)

    def get_device_resource(self, site_types, device_resources):
        """ Get device resource that corresponds to this class. """
        return device_resources.bel_pin(self.site, site_types[self.site],
                                        self.bel, self.pin)

    def to_tuple(self):
        """ Create tuple suitable for sorting this object.

        This tuple is used for sorting against other routing branch objects
        to generate a canonical routing tree.

        """
        return ('bel_pin', self.site, self.bel, self.pin)

    def __str__(self):
        return 'PhysicalBelPin({}, {}, {})'.format(
            repr(self.site),
            repr(self.bel),
            repr(self.pin),
        )


class PhysicalSitePin():
    """ Python class that represents a site pin in a physical net.

    site (str) - Site containing site pin
    pin (str) - Site pin in physical net.

    """

    def __init__(self, site, pin):
        self.site = site
        self.pin = pin

        self.branches = []

    def output_interchange(self, obj, string_id):
        """ Output this route segment and all branches beneth it.

        obj (physical_netlist.RouteBranch pycapnp object) -
            Object to write PhysicalBelPin into
        string_id (str -> int) - Function to intern strings into PhysNetlist
                                 string list.

        """
        obj.routeSegment.init('sitePin')
        obj.routeSegment.sitePin.site = string_id(self.site)
        obj.routeSegment.sitePin.pin = string_id(self.pin)

        descend_branch(obj, self, string_id)

    def get_device_resource(self, site_types, device_resources):
        """ Get device resource that corresponds to this class. """
        return device_resources.site_pin(self.site, site_types[self.site],
                                         self.pin)

    def to_tuple(self):
        """ Create tuple suitable for sorting this object.

        This tuple is used for sorting against other routing branch objects
        to generate a canonical routing tree.

        """
        return ('site_pin', self.site, self.pin)

    def __str__(self):
        return 'PhysicalSitePin({}, {})'.format(
            repr(self.site),
            repr(self.pin),
        )


class PhysicalPip():
    """ Python class that represents a active pip in a physical net.

    tile (str) - Tile containing pip
    wire0 (str) - Name of upstream wire to pip
    wire1 (str) - Name of downstream wire from pip
    forward (bool) - For bidirectional pips, is the connection from wire0 to
                     wire1 (forward=True) or wire1 to wire0 (forward=False).
    site (str) - name of site in case of Pseudo PIP

    """

    def __init__(self, tile, wire0, wire1, forward=True, site=None):
        self.tile = tile
        self.wire0 = wire0
        self.wire1 = wire1
        self.forward = forward
        self.site = site

        self.branches = []

    def output_interchange(self, obj, string_id):
        """ Output this route segment and all branches beneth it.

        obj (physical_netlist.RouteBranch pycapnp object) -
            Object to write PhysicalBelPin into
        string_id (str -> int) - Function to intern strings into PhysNetlist
                                 string list.

        """
        obj.routeSegment.init('pip')
        obj.routeSegment.pip.tile = string_id(self.tile)
        obj.routeSegment.pip.wire0 = string_id(self.wire0)
        obj.routeSegment.pip.wire1 = string_id(self.wire1)
        obj.routeSegment.pip.forward = self.forward
        obj.routeSegment.pip.isFixed = True

        descend_branch(obj, self, string_id)

    def get_device_resource(self, site_types, device_resources):
        """ Get device resource that corresponds to this class. """
        return device_resources.pip(self.tile, self.wire0, self.wire1)

    def to_tuple(self):
        """ Create tuple suitable for sorting this object.

        This tuple is used for sorting against other routing branch objects
        to generate a canonical routing tree.

        """
        return ('pip', self.tile, self.wire0, self.wire1)

    def __str__(self):
        return 'PhysicalPip({}, {}, {}, {}, {})'.format(
            repr(self.tile),
            repr(self.wire0),
            repr(self.wire1),
            repr(self.forward),
            repr(self.site),
        )


class PhysicalSitePip():
    """ Python class that represents a site pip in a physical net.

    This models site routing muxes and site inverters.

    site (str) - Site containing site pip
    bel (str) - Name of BEL that contains site pip
    pin (str) - Name of BEL pin that is the active site pip
    is_inverting (bool) - Indicates whether the site PIP is inverted

    """

    def __init__(self, site, bel, pin, is_inverting=False):
        self.site = site
        self.bel = bel
        self.pin = pin
        self.is_inverting = is_inverting

        self.branches = []

    def output_interchange(self, obj, string_id):
        """ Output this route segment and all branches beneth it.

        obj (physical_netlist.RouteBranch pycapnp object) -
            Object to write PhysicalBelPin into
        string_id (str -> int) - Function to intern strings into PhysNetlist
                                 string list.

        """
        obj.routeSegment.init('sitePIP')
        obj.routeSegment.sitePIP.site = string_id(self.site)
        obj.routeSegment.sitePIP.bel = string_id(self.bel)
        obj.routeSegment.sitePIP.pin = string_id(self.pin)
        obj.routeSegment.sitePIP.isInverting = self.is_inverting

        descend_branch(obj, self, string_id)

    def get_device_resource(self, site_types, device_resources):
        """ Get device resource that corresponds to this class. """
        return device_resources.site_pip(self.site, site_types[self.site],
                                         self.bel, self.pin)

    def to_tuple(self):
        """ Create tuple suitable for sorting this object.

        This tuple is used for sorting against other routing branch objects
        to generate a canonical routing tree.

        """
        return ('site_pip', self.site, self.bel, self.pin, self.is_inverting)

    def __str__(self):
        return 'PhysicalSitePip({}, {}, {}, {})'.format(
            repr(self.site),
            repr(self.bel),
            repr(self.pin),
            repr(self.is_inverting),
        )


def convert_tuple_to_object(site, tup):
    """ Convert physical netlist tuple to object.

    Physical netlist tuples are light weight ways to represent the physical
    net tree.

    site (Site) - Site object that tuple belongs too.
    tup (tuple) - Tuple that is either a site pin, bel pin, or site pip.

    Returns - PhysicalSitePin, PhysicalBelPin, or PhysicalSitePip based on
              tuple.

    >>> Site = namedtuple('Site', 'name')
    >>> site = Site(name='TEST_SITE')

    >>> site_pin = convert_tuple_to_object(site, ('site_pin', 'TEST_PIN'))
    >>> assert isinstance(site_pin, PhysicalSitePin)
    >>> site_pin.site
    'TEST_SITE'
    >>> site_pin.pin
    'TEST_PIN'
    >>> site_pin.branches
    []

    >>> bel_pin = convert_tuple_to_object(site, ('bel_pin', 'ABEL', 'APIN'))
    >>> assert isinstance(bel_pin, PhysicalBelPin)
    >>> bel_pin.site
    'TEST_SITE'
    >>> bel_pin.bel
    'ABEL'
    >>> bel_pin.pin
    'APIN'

    >>> site_pip = convert_tuple_to_object(site, ('site_pip', 'BBEL', 'BPIN'))
    >>> assert isinstance(site_pip, PhysicalSitePip)
    >>> site_pip.site
    'TEST_SITE'
    >>> site_pip.bel
    'BBEL'
    >>> site_pip.pin
    'BPIN'

    """
    if tup[0] == 'site_pin':
        _, pin = tup
        return PhysicalSitePin(site.name, pin)
    elif tup[0] == 'bel_pin':
        assert len(tup) == 3, tup
        _, bel, pin = tup
        return PhysicalBelPin(site.name, bel, pin)
    elif tup[0] == 'site_pip':
        _, bel, pin = tup
        return PhysicalSitePip(site.name, bel, pin)
    else:
        assert False, tup


def add_site_routing_children(site, parent_obj, parent_key, site_routing,
                              inverted_root):
    """ Convert site_routing map into Physical* python objects.

    site (Site) - Site object that contains site routing.
    parent_obj (Physical* python object) - Parent Physical* object to add new
                                         branches too.
    parent_key (tuple) - Site routing tuple for current parent_obj.
    site_routing (dict) - Map of parent site routing tuple to a set of
                          child site routing tuples.
    inverted_root (list) - List of physical net sources for the inverted
                           signal (e.g. a constant 1 net inverts to the
                           constant 0 net)

    """
    if parent_key in site_routing:
        for child in site_routing[parent_key]:
            if child[0] == 'inverter':
                if inverted_root is not None:
                    for child2 in site_routing[child]:
                        obj = convert_tuple_to_object(site, child2)
                        inverted_root.append(obj)

                        # Continue to descend, but no more inverted root.
                        # There should be no double site inverters (hopefully?)
                        add_site_routing_children(
                            site,
                            obj,
                            child2,
                            site_routing,
                            inverted_root=None)
                else:
                    add_site_routing_children(site, parent_obj, child,
                                              site_routing, inverted_root)
            else:
                obj = convert_tuple_to_object(site, child)
                parent_obj.branches.append(obj)

                add_site_routing_children(site, obj, child, site_routing,
                                          inverted_root)


def create_site_routing(site, net_roots, site_routing, constant_nets):
    """ Convert site_routing into map of nets to site local sources.

    site (Site) - Site object that contains site routing.
    net_roots (dict) - Map of root site routing tuples to the net name for
                       this root.
    site_routing (dict) - Map of parent site routing tuple to a set of
                          child site routing tuples.
    constant_nets (dict) - Map of 0/1 to their net name.

    Returns dict of nets to Physical* objects that represent the site local
    sources for that net.

    """
    nets = {}

    # Create a map of constant net names to their inverse.
    inverted_roots = {}

    for value, net_name in constant_nets.items():
        nets[net_name] = []
        inverted_roots[constant_nets[value ^ 1]] = nets[net_name]

    for root, net_name in net_roots.items():
        if net_name not in nets:
            nets[net_name] = []

        root_obj = convert_tuple_to_object(site, root)
        add_site_routing_children(site, root_obj, root, site_routing,
                                  inverted_roots.get(net_name, None))

        nets[net_name].append(root_obj)

    return nets


class PhysicalNetlist:
    """ Object that represents a physical netlist.

    part (str) - Part that this physical netlist is for.
    properties (dict) - Root level properties (if any) for physical netlist.

    """

    def __init__(self, part, properties={}):
        self.part = part
        self.properties = {}

        self.placements = []
        self.nets = []
        self.physical_cells = {}
        self.site_instances = {}
        self.null_net = []

    def add_site_instance(self, site_name, site_type):
        """ Add the site type for a site instance.

        All sites used in placement require a site type.

        If site instance was already added before, replaces the previous site
        type.

        """
        self.site_instances[site_name] = site_type

    def add_physical_cell(self, cell_name, cell_type):
        """ Add physical cell instance

        cell_name (str) - Name of physical cell instance
        cell_type (str) - Value of physical_netlist.PhysCellType

        If physical cell was already added before, replaces the previous cell
        type.

        """
        self.physical_cells[cell_name] = cell_type

    def add_placement(self, placement):
        """ Add physical_netlist.Placement python object to this physical netlist.

        placement (physical_netlist.Placement) - Placement to add.

        """
        self.placements.append(placement)

    def add_physical_net(self,
                         net_name,
                         sources,
                         stubs,
                         net_type=PhysicalNetType.Signal):
        """ Adds a physical net to the physical netlist.

        net_name (str) - Name of net.
        sources (list of
            physical_netlist.PhysicalBelPin - or -
            physical_netlist.PhysicalSitePin - or -
            physical_netlist.PhysicalSitePip - or -
            physical_netlist.PhysicalPip
            ) - Sources of this net.
        stubs (list of
            physical_netlist.PhysicalBelPin - or -
            physical_netlist.PhysicalSitePin - or -
            physical_netlist.PhysicalSitePip - or -
            physical_netlist.PhysicalPip
            ) - Stubs of this net.
        net_type (PhysicalNetType) - Type of net.

        """
        self.nets.append(
            PhysicalNet(
                name=net_name, type=net_type, sources=sources, stubs=stubs))

    def check_physical_nets(self, device_resources):
        """ Check physical nets for errors.

        Detects duplicate resources and invalid routing trees.

        """
        for net in self.nets:
            # RoutingTree does a check on the subtrees during construction.
            _ = RoutingTree(
                device_resources,
                self.site_instances,
                sources=net.sources,
                stubs=net.stubs)

    def stitch_physical_nets(self, device_resources, flatten=False):
        """ Stitch supplied physical nets into routing trees.

        flatten (bool) - If true, existing routing trees are flattened before
                         stitching process.  This can be useful for testing,
                         or if the input routing tree was invalid and needs to
                         be reconstructed.

        """
        for idx, net in enumerate(self.nets):
            segments = net.sources + net.stubs
            if flatten:
                segments = flatten_segments(segments)

            sources, stubs = stitch_segments(device_resources,
                                             self.site_instances, segments)

            self.nets[idx] = PhysicalNet(
                name=net.name,
                type=net.type,
                sources=sources,
                stubs=stubs,
            )

    def get_normalized_tuple_tree(self, device_resources):
        """ Return physical nets in canonical tuple form.

        Returns a dictionary of net names to tuple trees.  Each value of the
        dictionary is a two tuple or the stubs and sources for the net. Each
        stub and source is a two tuple of the current segment of the routing
        tree, and a tuple of children from that segment.

        The method is mostly useful for comparing routing trees for equality,
        as equivelent routing trees will generate the same tuple tree.

        """
        output = {}

        for net in self.nets:
            routing_tree = RoutingTree(
                device_resources,
                self.site_instances,
                sources=net.sources,
                stubs=net.stubs)

            routing_tree.normalize_tree()
            assert net.name not in output
            output[net.name] = routing_tree.get_tuple_tree()

        return output

    def set_null_net(self, stubs):
        self.null_net = stubs

    @staticmethod
    def read_from_capnp(f, interchange, *args, **kwargs):
        """ Reads a capnp logical netlist into PhysicalNetlist object.

        f (file-like)
            File to be read

        interchange (interchange_capnp.Interchange)
            Interchange object holding capnp schema's for the FPGA interchange
            format.

        compression_format (interchange_capnp.CompressionFormat)
            What compression format to use.  Default is
            interchange_capnp.DEFAULT_COMPRESSION_TYPE

        is_packed (bool)
            Whether capnp is packed or not.  Default is
            interchange_capnp.IS_PACKED.

        Returns PhysicalNetlist created from input file.

        """
        return interchange.read_physical_netlist(f, *args, **kwargs)

    def convert_to_capnp(self, interchange):
        """ Convert PhysicalNetlist object into capnp object.

        Use interchange_capnp.write_capnp_file to write to disk or other
        storage.

        interchange (interchange_capnp.Interchange)
            Interchange object holding capnp schema's for the FPGA interchange
            format.

        """
        return interchange.output_physical_netlist(self)


def chain_branches(segments):
    """ Convert a linear routing segment chain into the branch structure.

    Returns the root of the tree.

    """
    for parent, child in zip(segments[:-1], segments[1:]):
        parent.branches.append(child)

    return segments[0]


def chain_pips(tile, wires):
    """ Chain a set of pips into a branch tree structure. """
    segments = []

    for wire0, wire1 in zip(wires[:-1], wires[1:]):
        segments.append(
            PhysicalPip(tile=tile, wire0=wire0, wire1=wire1, forward=True))

    return tuple(segments)
