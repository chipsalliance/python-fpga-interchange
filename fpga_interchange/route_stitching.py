def create_id_map(id_to_segment, segments):
    for segment in segments:
        segment_id = id(segment)
        assert segment_id not in id_to_segment
        id_to_segment[segment_id] = segment

        create_id_map(id_to_segment, segment.branches)


def check_tree(routing_tree, segment):
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


class RoutingTree():
    def __init__(self, device_resources, site_types, segments):
        self.id_to_segment = {}
        self.id_to_device_resource = {}

        self.stubs = []
        self.sources = []

        self.connections = {}

        create_id_map(self.id_to_segment, segments)

        for segment_id, segment in self.id_to_segment.items():
            self.id_to_device_resource[
                segment_id] = segment.get_device_resource(
                    site_types, device_resources)

        self.check_trees()

        for segment in segments:
            if self.get_device_resource(segment).is_root():
                self.sources.append(segment)
            else:
                self.stubs.append(segment)

    def get_device_resource(self, segment):
        return self.id_to_device_resource[id(segment)]

    def check_trees(self):
        """ Check that the routing tree at and below obj is valid.

        This method should be called after all route segments have been added
        to the node cache.

        """
        for stub in self.stubs:
            check_tree(self, stub)

        for source in self.sources:
            check_tree(self, source)

    def connections_for_segment_id(self, segment_id):
        resource = self.id_to_device_resource[segment_id]
        for site_wire in resource.site_wires():
            yield site_wire

        for node in resource.nodes():
            yield node

    def build_connections(self):
        for segment_id in self.id_to_segment.keys():
            for connection in self.connections_for_segment_id(segment_id):
                if connection not in self.connections:
                    self.connections[connection] = set()
                self.connections[connection].add(segment_id)

    def attach(self, parent_id, child_id):
        """ Attach a child routing tree to the routing tree for parent. """
        self.id_to_segment[parent_id].branches.append(self.id_to_obj[child_id])

    def check_count(self):
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
            for segment_id in routing_tree.connections[connection]:
                if segment_id not in id_to_idx:
                    continue

                # There should never be a loop because root_obj_id should not
                # be in the id_to_idx map once it is stitched into another tree.
                assert root_obj_id != segment_id

                if not routing_tree.is_connected(root_obj_id, segment_id):
                    continue

                idx = id_to_idx[segment_id]
                assert idx not in stitched_stubs
                stitched_stubs.add(idx)
                objs_to_attach.append((id(branch), segment_id))


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
    objs_to_attach = []

    stitched_stubs = set()
    for parent in parents:
        attach_candidates(
            routing_tree=routing_tree,
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

        routing_tree.attach(branch_id, child_id)

        stitched_stubs.add(id_to_idx[child_id])
        del id_to_idx[child_id]

    # Return the newly stitched stubs, so that they form the new parent list.
    return stitched_stubs


def stitch_segments(device_resources, site_types, segments):
    routing_tree = RoutingTree(device_resources, site_types, segments)
    routing_tree.build_connections()

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
