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
""" This file defines the RoutingTree class which can be used for constructing
routing trees for route segments from the fpga_interchange.physical_netlist
class PhysicalBelPin/PhysicalSitePin/PhysicalSitePip/PhysicalPip.

Use of the RoutingTree requires having the DeviceResources class loaded for
the relevant part for the design.  Use
interchange_capnp.Interchange.read_device_resources to load a device resource
file.

"""


def create_id_map(id_to_segment, segments):
    """ Create or update dict from object ids of segments to segments. """
    for segment in segments:
        segment_id = id(segment)
        assert segment_id not in id_to_segment
        id_to_segment[segment_id] = segment

        create_id_map(id_to_segment, segment.branches)


def check_tree(routing_tree, segment):
    """ Recursively checks a routing tree.

    Checks for:
     - Circular routing trees
     - Child segments are connected to their parents.
    """

    # Check for circular routing tree
    for _ in yield_branches(segment):
        pass

    # Ensure children are connected to parent.
    root_resource = routing_tree.get_device_resource(segment)
    for child in segment.branches:
        child_resource = routing_tree.get_device_resource(child)

        assert root_resource.is_connected(child_resource), (str(segment),
                                                            str(child),
                                                            root_resource,
                                                            child_resource)

        check_tree(routing_tree, child)


def yield_branches(routing_branch):
    """ Yield all routing branches starting from the given route segment.

    This will yield the input route branch in addition to its children.

    An AssertionError will be raised for a circular route is detected.

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


def sort_branches(branches):
    """ Sort branches by the branch tuple.

    The branch tuple is:
        ('bel_pin'/'site_pin'/'site_pip'/'pip', <site>/<tile>, ...)

    so sorting in this way ensures that BEL pins are grouped, etc.
    This also canonicalize the branch order, which makes comparing trees each,
    just normalize both trees, and compare the result.

    """
    branches.sort(key=lambda item: item.to_tuple())


def get_tuple_tree(root_branch):
    """ Convert a rout branch in a two tuple. """
    return root_branch.to_tuple(), tuple(
        get_tuple_tree(branch) for branch in root_branch.branches)


class RoutingTree():
    """ Utility class for managing stitching of a routing tree. """

    def __init__(self, device_resources, site_types, stubs, sources):
        # Check that no duplicate routing resources are present.
        tuple_to_id = {}
        for stub in stubs:
            for branch in yield_branches(stub):
                tup = branch.to_tuple()
                assert tup not in tuple_to_id, tup
                tuple_to_id[tup] = id(branch)

        for source in sources:
            for branch in yield_branches(source):
                tup = branch.to_tuple()
                assert tup not in tuple_to_id, tup
                tuple_to_id[tup] = id(branch)

        self.id_to_segment = {}
        self.id_to_device_resource = {}

        self.stubs = stubs
        self.sources = sources

        self.connections = None

        # Populate id_to_segment and id_to_device_resource maps.
        create_id_map(self.id_to_segment, self.stubs)
        create_id_map(self.id_to_segment, self.sources)

        for segment_id, segment in self.id_to_segment.items():
            self.id_to_device_resource[
                segment_id] = segment.get_device_resource(
                    site_types, device_resources)

        # Verify initial input makes sense.
        self.check_trees()

    def segment_for_id(self, segment_id):
        """ Get routing segment based on the object id of the routing segment. """
        return self.id_to_segment[segment_id]

    def normalize_tree(self):
        """ Normalize the routing tree by sorted element. """
        sort_branches(self.stubs)
        sort_branches(self.sources)

        for stub in self.stubs:
            for branch in yield_branches(stub):
                sort_branches(branch.branches)

        for source in self.sources:
            for branch in yield_branches(source):
                sort_branches(branch.branches)

    def get_tuple_tree(self):
        """ Get tuple tree representation of the current routing tree.

        This is suitable for equality checking if normalized with
        normalize_tree.

        """
        return (tuple(get_tuple_tree(stub) for stub in self.stubs),
                tuple(get_tuple_tree(source) for source in self.sources))

    def get_device_resource_for_id(self, segment_id):
        """ Get the device resource that corresponds to the segment id given. """
        return self.id_to_device_resource[segment_id]

    def get_device_resource(self, segment):
        """ Get the device resource that corresponds to the segment given. """
        return self.id_to_device_resource[id(segment)]

    def check_trees(self):
        """ Check that the routing tree at and below obj is valid.

        This method should be called after all route segments have been added
        to the node cache.

        """
        for stub in self.stubs:
            check_tree(self, stub)

        for source in self.sources:
            assert self.get_device_resource(source).is_root(), source
            check_tree(self, source)

    def connections_for_segment_id(self, segment_id):
        """ Yield all connection resources connected to segment id given. """
        resource = self.id_to_device_resource[segment_id]
        for site_wire in resource.site_wires():
            yield site_wire

        for node in resource.nodes():
            yield node

    def build_connections(self):
        """ Create a dictionary of connection resources to segment ids. """
        self.connections = {}
        for segment_id in self.id_to_segment.keys():
            for connection in self.connections_for_segment_id(segment_id):
                if connection not in self.connections:
                    self.connections[connection] = set()
                self.connections[connection].add(segment_id)

    def get_connection(self, connection_resource):
        """ Get list of segment ids connected to connection_resource. """

        if self.connections is None:
            self.build_connections()

        return self.connections[connection_resource]

    def reroot(self):
        """ Determine which routing segments are roots and non-roots.

        Repopulates stubs and sources list with new roots and non-root
        segments.

        """
        if self.connections is None:
            self.build_connections()

        segments = self.stubs + self.sources
        self.stubs.clear()
        self.sources.clear()

        source_segment_ids = set()

        # Example each connection and find the best root.
        for segment_ids in self.connections.values():
            root_priority = None
            root = None
            root_count = 0
            for segment_id in segment_ids:
                resource = self.get_device_resource_for_id(segment_id)
                if resource.is_root():
                    possible_root_priority = resource.root_priority()

                    if root is None:
                        root_priority = possible_root_priority
                        root = segment_id
                        root_count = 1
                    elif possible_root_priority < root_priority:
                        root_priority = possible_root_priority
                        root = segment_id
                        root_count = 1
                    elif possible_root_priority == root_priority:
                        root_count += 1

            if root is not None:
                # Generate an error if multiple segments could be a root.
                # This should only occur near IO pads.  In most cases, the
                # root should be the only Direction.Output BEL pin on the site
                # wire.
                assert root_count == 1
                source_segment_ids.add(root)

        for segment in segments:
            if id(segment) in source_segment_ids:
                self.sources.append(segment)
            else:
                self.stubs.append(segment)

    def attach(self, parent_id, child_id):
        """ Attach a child routing tree to the routing tree for parent. """
        assert self.id_to_device_resource[parent_id].is_connected(
            self.id_to_device_resource[child_id])
        self.id_to_segment[parent_id].branches.append(
            self.id_to_segment[child_id])

    def check_count(self):
        """ Verify that every segment is reachable from stubs and sources list. 

        This check ensures no routing segment is orphaned during processing.

        """
        count = 0

        for stub in self.stubs:
            for _ in yield_branches(stub):
                count += 1

        for source in self.sources:
            for _ in yield_branches(source):
                count += 1

        assert len(self.id_to_segment) == count


def attach_candidates(routing_tree, id_to_idx, stitched_stubs, objs_to_attach,
                      route_branch, visited):
    """ Attach children of branches in the routing tree route_branch.

    routing_tree : RoutingTree
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
        passed to routing_tree.attach to join the trees.

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

        for connection in routing_tree.connections_for_segment_id(id(branch)):
            for segment_id in routing_tree.get_connection(connection):
                if id(branch) == segment_id:
                    continue

                if segment_id not in id_to_idx:
                    continue

                # There should never be a loop because root_obj_id should not
                # be in the id_to_idx map once it is stitched into another tree.
                assert root_obj_id != segment_id

                if not routing_tree.get_device_resource(branch).is_connected(
                        routing_tree.get_device_resource_for_id(segment_id)):
                    continue

                idx = id_to_idx[segment_id]
                if idx in stitched_stubs:
                    assert segment_id in objs_to_attach

                    proposed_parent = id(branch)
                    old_parent = objs_to_attach[segment_id]
                    assert old_parent == proposed_parent, (
                        str(routing_tree.segment_for_id(proposed_parent)),
                        str(routing_tree.segment_for_id(old_parent)),
                        str(routing_tree.segment_for_id(segment_id)))
                else:
                    stitched_stubs.add(idx)
                    objs_to_attach[segment_id] = id(branch)


def attach_from_parents(routing_tree, id_to_idx, parents, visited):
    """ Attach children routing tree starting from list of parent routing trees.

    routing_tree : RoutingTree
        A node cache that contains all routing branches in the net.

    id_to_idx : dict object id to int
        Map of object id to idx in a list of unstitched routing branches.

    parents : list of PhysicalBelPin/PhysicalSitePin/PhysicalSitePip/PhysicalPip
        Roots of routing tree to search for children trees.

    visited : set of ids to routing branches.

    Returns set of indicies to stitched stubs.

    """
    objs_to_attach = {}

    stitched_stubs = set()
    for parent in parents:
        attach_candidates(
            routing_tree=routing_tree,
            id_to_idx=id_to_idx,
            stitched_stubs=stitched_stubs,
            objs_to_attach=objs_to_attach,
            route_branch=parent,
            visited=visited)

    for child_id, branch_id in objs_to_attach.items():
        # The branch_id should not be in the id_to_idx map, because it should
        # be an outstanding stub.
        assert branch_id not in id_to_idx

        # The child_id should be in the id_to_idx map, because it should be an
        # outstanding stub.
        assert child_id in id_to_idx

        routing_tree.attach(branch_id, child_id)

        stitched_stubs.add(id_to_idx[child_id])
        del id_to_idx[child_id]

    # Return the newly stitched stubs, so that they form the new parent list.
    return stitched_stubs


def stitch_segments(device_resources, site_types, segments):
    """ Stitch segments of the routing tree into trees rooted from net sources. """
    routing_tree = RoutingTree(
        device_resources, site_types, stubs=segments, sources=[])
    routing_tree.reroot()

    # Create a id to idx map so that stitching can be deferred when walking
    # trees
    id_to_idx = {}
    for idx, stub in enumerate(routing_tree.stubs):
        assert idx not in id_to_idx
        id_to_idx[id(stub)] = idx

    # Initial set of tree parents are just the sources
    parents = routing_tree.sources
    stitched_stubs = set()

    # Track visited nodes, as it is expected to never visit a route branch
    # more than once.
    visited = set()

    # Continue iterating until no more stubs are stitched.
    while len(parents) > 0:
        # Starting from the parents of the current tree, add stubs the
        # descend from this set, and create a new set of parents from those
        # stubs.
        newly_stitched_stubs = attach_from_parents(routing_tree, id_to_idx,
                                                   parents, visited)

        # Mark the newly stitched stubs to be removed.
        stitched_stubs |= newly_stitched_stubs

        # New set of parents using from the newly stitched stubs.
        parents = [routing_tree.stubs[idx] for idx in newly_stitched_stubs]

    # Remove stitched stubs from stub list
    for idx in sorted(stitched_stubs, reverse=True):
        del routing_tree.stubs[idx]

    # Make sure new trees are sensible.
    routing_tree.check_trees()
    routing_tree.check_count()

    return routing_tree.sources, routing_tree.stubs


def flatten_segments(segments):
    """ Take a list of routing segments and flatten out any children. """
    output = []

    for segment in segments:
        for branch in yield_branches(segment):
            output.append(branch)

    for segment in output:
        segment.branches.clear()

    return output
