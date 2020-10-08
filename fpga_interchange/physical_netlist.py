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

import enum
from collections import namedtuple
from .logical_netlist import Direction


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
        if bel != self.bel:
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

    def __init__(self, site, bel, pin, direction):
        self.site = site
        self.bel = bel
        self.pin = pin
        self.site_source = False

        if direction == 'inout':
            self.direction = Direction.Inout
        elif direction == 'input':
            self.direction = Direction.Input
        elif direction == 'output':
            self.direction = Direction.Output
        else:
            assert direction == 'site_source'
            self.direction = Direction.Output
            self.site_source = True

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

    def nodes(self, cursor, site_type_pins):
        return []

    def is_root(self):
        return self.direction in [Direction.Output, Direction.Inout
                                  ] and not self.site_source

    def __str__(self):
        if self.direction == Direction.Output:
            if self.site_source:
                direction = 'site_source'
            else:
                direction = 'output'
        elif self.direction == Direction.Input:
            direction = 'input'
        else:
            assert self.direction == Direction.Inout, self.direction
            direction = 'inout'

        return 'PhysicalBelPin({}, {}, {}, {})'.format(
            repr(self.site),
            repr(self.bel),
            repr(self.pin),
            direction,
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

    def nodes(self, cursor, site_type_pins):
        cursor.execute(
            """
WITH a_site_instance(site_pkey, phy_tile_pkey) AS (
    SELECT site_pkey, phy_tile_pkey
    FROM site_instance
    WHERE name = ?
)
SELECT node_pkey FROM wire WHERE
    phy_tile_pkey = (SELECT phy_tile_pkey FROM a_site_instance)
AND
    wire_in_tile_pkey = (
        SELECT pkey FROM wire_in_tile WHERE
            site_pkey = (SELECT site_pkey FROM a_site_instance)
        AND
            site_pin_pkey IN (SELECT pkey FROM site_pin WHERE name = ?)
    );
        """, (self.site, site_type_pins[self.site, self.pin]))

        results = cursor.fetchall()
        assert len(results) == 1, (results, self.site, self.pin,
                                   site_type_pins[self.site, self.pin])
        return [results[0][0]]

    def is_root(self):
        return False

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

    """

    def __init__(self, tile, wire0, wire1, forward):
        self.tile = tile
        self.wire0 = wire0
        self.wire1 = wire1
        self.forward = forward

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

    def nodes(self, cursor, site_type_pins):
        cursor.execute("""SELECT pkey FROM phy_tile WHERE name = ?;""",
                       (self.tile, ))
        (phy_tile_pkey, ) = cursor.fetchone()

        cursor.execute(
            """
SELECT node_pkey FROM wire WHERE
    phy_tile_pkey = ?
AND
    wire_in_tile_pkey IN (SELECT pkey FROM wire_in_tile WHERE name = ?);""",
            (phy_tile_pkey, self.wire0))
        (node0_pkey, ) = cursor.fetchone()

        cursor.execute(
            """
SELECT node_pkey FROM wire WHERE
    phy_tile_pkey = ?
AND
    wire_in_tile_pkey IN (SELECT pkey FROM wire_in_tile WHERE name = ?);""",
            (phy_tile_pkey, self.wire1))
        (node1_pkey, ) = cursor.fetchone()

        return [node0_pkey, node1_pkey]

    def is_root(self):
        return False

    def __str__(self):
        return 'PhysicalPip({}, {}, {}, {})'.format(
            repr(self.tile),
            repr(self.wire0),
            repr(self.wire1),
            repr(self.forward),
        )


class PhysicalSitePip():
    """ Python class that represents a site pip in a physical net.

    This models site routing muxes and site inverters.

    site (str) - Site containing site pip
    bel (str) - Name of BEL that contains site pip
    pin (str) - Name of BEL pin that is the active site pip

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
        obj.routeSegment.init('sitePIP')
        obj.routeSegment.sitePIP.site = string_id(self.site)
        obj.routeSegment.sitePIP.bel = string_id(self.bel)
        obj.routeSegment.sitePIP.pin = string_id(self.pin)

        descend_branch(obj, self, string_id)

    def nodes(self, cursor, site_type_pins):
        return []

    def is_root(self):
        return False

    def __str__(self):
        return 'PhysicalSitePip({}, {}, {})'.format(
            repr(self.site),
            repr(self.bel),
            repr(self.pin),
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

    >>> bel_pin = convert_tuple_to_object(site, ('bel_pin', 'ABEL', 'APIN', 'input'))
    >>> assert isinstance(bel_pin, PhysicalBelPin)
    >>> bel_pin.site
    'TEST_SITE'
    >>> bel_pin.bel
    'ABEL'
    >>> bel_pin.pin
    'APIN'
    >>> bel_pin.direction
    <Direction.Input: 0>

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
        assert len(tup) == 4, tup
        _, bel, pin, direction = tup
        return PhysicalBelPin(site.name, bel, pin, direction)
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


class NodeCache():
    """ Cache of route segment to node_pkey and node_pkey to route segments. """

    def __init__(self):
        self.id_to_obj = {}
        self.id_to_nodes = {}
        self.node_to_ids = {}

    def add_route_branch(self, obj, cursor, site_type_pins):
        """ Add route branch to cache.

        obj : PhysicalBelPin/PhysicalSitePin/PhysicalSitePip/PhysicalPip
            Add route segment to node cache.

        cursor : sqlite3.Cursor
            Cursor to connection database.

        site_type_pins
            Map of used site pin to the site pin default name.

            The interchange uses the site pin name for the particular type in
            use, e.g. RAMB36E1.  The connection database has the site pin
            names for the default site type (e.g. RAMBFIFO36E1).
            site_type_pins maps the site specific type back to the default
            type found in the connection database.

            FIXME: If the connection database had the site pins for each
            alternative site type, this map would no longer be required.
        """
        obj_id = id(obj)
        assert obj_id not in self.id_to_obj

        self.id_to_obj[obj_id] = obj
        self.id_to_nodes[obj_id] = set(obj.nodes(cursor, site_type_pins))
        for node in self.id_to_nodes[obj_id]:
            if node not in self.node_to_ids:
                self.node_to_ids[node] = set()

            self.node_to_ids[node].add(obj_id)

        for child_branch in obj.branches:
            self.add_route_branch(child_branch, cursor, site_type_pins)

    def check_tree(self, obj, parent=None):
        """ Check that the routing tree at and below obj is valid.

        This method should be called after all route segments have been added
        to the node cache.

        """

        if parent is not None:
            nodes = self.id_to_nodes[id(obj)]
            parent_nodes = self.id_to_nodes[id(parent)]

            if nodes and parent_nodes:
                assert len(nodes & parent_nodes) > 0, (parent, obj)

        for child in obj.branches:
            self.check_tree(child, parent=obj)

    def attach(self, parent_id, child_id):
        """ Attach a child routing tree to the routing tree for parent. """
        self.id_to_obj[parent_id].branches.append(self.id_to_obj[child_id])

    def nodes_for_branch(self, obj):
        """ Return the node pkey's attached to the routing branch in obj. """
        return self.id_to_nodes[id(obj)]


def yield_branches(routing_branch):
    """ Yield all routing branches starting from the given route segment.

    This will yield the input route branch in addition to its children.

    """
    objs = set()

    def descend(obj):
        obj_id = id(obj)
        assert obj_id not in objs
        objs.add(obj_id)

        yield obj

        for seg in obj.branches:
            for s in descend(seg):
                yield s

    for s in descend(routing_branch):
        yield s


def duplicate_check(sources, stubs):
    """ Check routing sources and stubs for duplicate objects.

    Returns the total number of routing branches in the sources and stubs list.

    """
    objs = set()

    def descend(obj):
        obj_id = id(obj)
        assert obj_id not in objs

        objs.add(obj_id)

        for obj in obj.branches:
            descend(obj)

    for obj in sources:
        descend(obj)

    for obj in stubs:
        descend(obj)

    return len(objs)


def attach_candidates(node_cache, id_to_idx, stitched_stubs, objs_to_attach,
                      route_branch, visited):
    """ Attach children of branches in the routing tree route_branch.

    node_cache : NodeCache
        A node cache that contains all routing branches in the net.

    id_to_idx : dict object id to int
        Map of object id to idx in a list of unstitched routing branches.

    stitched_stubs : set of int
        Set of indicies of stubs that have been stitched.  Used to track which
        stubs have been stitched into the tree, and verify stubs are not
        stitched twice into the tree.

    objs_to_attach : list of parent object id to child object id
        When attach_candidates finds a stub that should be stitched into the
        routing tree, rather than stitch it immediately, it adds a parent of
        (id(parent), id(child)) to objs_to_attach.  This deferal enables the
        traversal of the input routing tree without modification.

        After attach_candidates returns, elements of objs_to_attach should be
        passed to node_cache.attach to join the trees.

    obj : PhysicalBelPin/PhysicalSitePin/PhysicalSitePip/PhysicalPip
        Root of routing tree to iterate over to identify candidates to attach
        to routing tree..

    visited : set of ids to routing branches.

    """
    root_obj_id = id(route_branch)
    assert root_obj_id not in id_to_idx

    for branch in yield_branches(route_branch):
        # Make sure each route branch is only visited once.
        assert id(branch) not in visited
        visited.add(id(branch))

        for node in node_cache.nodes_for_branch(branch):
            for obj_id in node_cache.node_to_ids[node]:
                if obj_id not in id_to_idx:
                    continue

                # There should never be a loop because root_obj_id should not
                # be in the id_to_idx map once it is stitched into another tree.
                assert root_obj_id != obj_id

                idx = id_to_idx[obj_id]
                assert idx not in stitched_stubs
                stitched_stubs.add(idx)
                objs_to_attach.append((id(branch), obj_id))


def attach_from_parents(node_cache, id_to_idx, parents, visited):
    """ Attach children routing tree starting from list of parent routing trees.

    node_cache : NodeCache
        A node cache that contains all routing branches in the net.

    id_to_idx : dict object id to int
        Map of object id to idx in a list of unstitched routing branches.

    parents : list of PhysicalBelPin/PhysicalSitePin/PhysicalSitePip/PhysicalPip
        Roots of routing tree to search for children trees.

    visited : set of ids to routing branches.

    Returns set of indicies to stitched stubs.

    """
    objs_to_attach = []

    stitched_stubs = set()
    for parent in parents:
        attach_candidates(
            node_cache=node_cache,
            id_to_idx=id_to_idx,
            stitched_stubs=stitched_stubs,
            objs_to_attach=objs_to_attach,
            route_branch=parent,
            visited=visited)

    for branch_id, child_id in objs_to_attach:
        # The branch_id should not be in the id_to_idx map, because it should
        # be an outstanding stub.
        assert branch_id not in id_to_idx

        # The child_id should be in the id_to_idx map, because it should be an
        # outstanding stub.
        assert child_id in id_to_idx

        node_cache.attach(branch_id, child_id)

        stitched_stubs.add(id_to_idx[child_id])
        del id_to_idx[child_id]

    # Return the newly stitched stubs, so that they form the new parent list.
    return stitched_stubs


def stitch_stubs(stubs, cursor, site_type_pins):
    """ Stitch stubs of the routing tree into trees routed from net sources. """
    sources = []

    # Verify input stubs have no loops.
    count = duplicate_check(sources, stubs)

    stitched_stubs = set()

    node_cache = NodeCache()

    # Populate the node cache and move root stubs to the sources list.
    for idx, stub in enumerate(stubs):
        if stub.is_root():
            stitched_stubs.add(idx)
            sources.append(stub)

        node_cache.add_route_branch(stub, cursor, site_type_pins)

    # Make sure all stubs appear valid before stitching.
    for stub in stubs:
        node_cache.check_tree(stub)

    # Remove root stubs now that they are in the sources list.
    for idx in sorted(stitched_stubs, reverse=True):
        del stubs[idx]

    # Create a id to idx map so that stitching can be deferred when walking
    # trees
    id_to_idx = {}
    for idx, stub in enumerate(stubs):
        assert idx not in id_to_idx
        id_to_idx[id(stub)] = idx

    # Initial set of tree parents are just the sources
    parents = sources
    stitched_stubs = set()

    # Track visited nodes, as it is expected to never visit a route branch
    # more than once.
    visited = set()

    # Continue iterating until no more stubs are stitched.
    while len(parents) > 0:
        # Starting from the parents of the current tree, add stubs the
        # descend from this set, and create a new set of parents from those
        # stubs.
        newly_stitched_stubs = attach_from_parents(node_cache, id_to_idx,
                                                   parents, visited)

        # Mark the newly stitched stubs to be removed.
        stitched_stubs |= newly_stitched_stubs

        # New set of parents using from the newly stitched stubs.
        parents = [stubs[idx] for idx in newly_stitched_stubs]

    # Remove stitched stubs from stub list
    for idx in sorted(stitched_stubs, reverse=True):
        del stubs[idx]

    # Make sure new trees are sensible.
    for source in sources:
        node_cache.check_tree(source)

    # Make sure final source and stub lists have no duplicates.
    assert count == duplicate_check(sources, stubs)

    return sources, stubs


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

    def set_null_net(self, stubs):
        self.null_net = stubs
