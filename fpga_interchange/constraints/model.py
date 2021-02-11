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
from fpga_interchange.constraints.sat import ExclusiveStateGroup, Solver


def get_prefix(matchers, other):
    """ Get prefix based on matchers for a given object. """
    name = None
    priority = None

    for matcher in matchers:
        matcher_prefix = matcher.prefix(other)
        matcher_priority = matcher.priority()
        if name is None or matcher_priority > priority:
            name = matcher_prefix
            priority = matcher_priority

    return name


class Tag():
    def __init__(self, name, states, default, matchers):
        assert len(set(states)) == len(states)

        self.name = name
        self.states = sorted(states)
        self.default = default
        self.matchers = matchers

    def match(self, other):
        return any(matcher.match(other) for matcher in self.matchers)

    def prefix(self, other):
        return get_prefix(self.matchers, other)

    def __repr__(self):
        return "Tag(name={}, states={}, default={}, matchers={})".format(
            repr(self.name), repr(self.states), repr(self.default),
            repr(self.matchers))


BelPin = namedtuple('BelPin', 'pin tag')


class RoutedTag():
    def __init__(self, name, routing_bel, bel_pins):
        assert len(set(pin.pin for pin in bel_pins)) == len(bel_pins)

        self.name = name
        self.routing_bel = routing_bel
        self.bel_pins = sorted(bel_pins)

    def match(self, other):
        return any(matcher.match(other) for matcher in self.matchers)

    def prefix(self, other):
        return get_prefix(self.matchers, other)

    def __repr__(self):
        return "RoutedTag({}, {}, {})".format(
            repr(self.name), repr(self.routing_bel), repr(self.bel_pins))


class TileTypeMatcher():
    """ A matcher that matches a tile type. """

    def __init__(self, tile_type):
        self.tile_type = tile_type

    def __repr__(self):
        return 'TileTypeMatcher({})'.format(repr(self.tile_type))

    def match(self, other):
        return other.is_tile_type(self.tile_type)

    def prefix(self, other):
        if self.match(other):
            return other.tile_prefix()

    def is_tile_type(self, tile_type):
        return self.tile_type == tile_type

    def is_site_type(self, site_type):
        return False

    def is_bel(self, site_type, bel):
        return False

    def priority(self):
        return 0


class SiteTypeMatcher():
    """ A matcher that matches a site type. """

    def __init__(self, site_type):
        self.site_type = site_type

    def __repr__(self):
        return 'SiteTypeMatcher({})'.format(repr(self.site_type))

    def match(self, other):
        return other.is_site_type(self.site_type)

    def prefix(self, other):
        if self.match(other):
            return other.site_prefix()

    def is_tile_type(self, tile_type):
        return False

    def is_site_type(self, site_type):
        return self.site_type == site_type

    def is_bel(self, site_type, bel):
        return False

    def priority(self):
        return 1


class BelMatcher():
    """ A matcher that matches a BEL. """

    def __init__(self, site_type, bel):
        self.site_type = site_type
        self.bel = bel

    def __repr__(self):
        return 'BelMatcher({}, {})'.format(
            repr(self.site_type), repr(self.bel))

    def match(self, other):
        return other.is_bel(self.site_type, self.bel)

    def prefix(self, other):
        if self.match(other):
            return other.bel_prefix()

    def is_tile_type(self, tile_type):
        return False

    def is_site_type(self, site_type):
        return self.site_type == site_type

    def is_bel(self, site_type, bel):
        return self.site_type == site_type and self.bel == bel

    def priority(self):
        return 2


class ImpliesConstraint():
    """ Constraint for a SAT variable that implies a state in a group. """

    def __init__(self, tag, state, matchers, port):
        self.tag = tag
        self.state = state
        self.matchers = matchers
        self.port = port

    def __repr__(self):
        return 'ImpliesConstraint({}, {}, {}, {})'.format(
            repr(self.tag), repr(self.state), repr(self.matchers),
            repr(self.port))

    def match(self, other):
        """ Return true if other matches this constraint. """
        return any(matcher.match(other) for matcher in self.matchers)

    def tag_for(self, tags, other):
        tag = tags[self.tag]
        tag_prefix = tag.prefix(other)
        assert tag_prefix is not None, (self.tag, other)
        return '{}.{}'.format(tag_prefix, self.tag)

    def clauses_for(self, source_variable, state_group):
        """ Yield SAT clauses for this constraint. """
        for clause in state_group.implies_clause(source_variable, self.state):
            yield clause


class RequiresConstraint():
    """ Constraint for a SAT variable that requires states in a group. """

    def __init__(self, tag, states, matchers, port):
        self.tag = tag
        self.states = states
        self.matchers = matchers
        self.port = port

    def __repr__(self):
        return 'RequiresConstraint({}, {}, {}, {})'.format(
            repr(self.tag), repr(self.state), repr(self.matchers),
            repr(self.port))

    def match(self, other):
        """ Return true if other matches this constraint. """
        return any(matcher.match(other) for matcher in self.matchers)

    def tag_for(self, tags, other):
        tag = tags[self.tag]
        tag_prefix = tag.prefix(other)
        assert tag_prefix is not None
        return '{}.{}'.format(tag_prefix, self.tag)

    def clauses_for(self, source_variable, state_group):
        """ Yield SAT clauses for this constraint. """
        for clause in state_group.requires_clause(source_variable,
                                                  self.states):
            yield clause


class CellConstraints():
    """ Object to hold constraints for cell types. """

    def __init__(self, cell):
        self.cell = cell
        self.constraints = []

    def for_placement(self, placement):
        """ Yields constraints that apply for a specific placement. """
        for constraint in self.constraints:
            if constraint.match(placement):
                yield constraint


class Placement():
    """ Object to hold a placement location. """

    def __init__(self, tile, site, tile_type, site_type, bel):
        self.tile = tile
        self.site = site
        self.tile_type = tile_type
        self.site_type = site_type
        self.bel = bel

    def __repr__(self):
        return 'Placement({}, {}, {}, {}, {})'.format(
            repr(self.tile), repr(self.site), repr(self.tile_type),
            repr(self.site_type), repr(self.bel))

    def match(self, other):
        return other.is_bel(self.site_type, self.bel)

    def is_tile_type(self, tile_type):
        return self.tile_type == tile_type

    def is_site_type(self, site_type):
        return self.site_type == site_type

    def is_bel(self, site_type, bel):
        return self.site_type == site_type and self.bel == bel

    def tile_prefix(self):
        return self.tile

    def site_prefix(self):
        return self.site

    def bel_prefix(self):
        return '{}.{}'.format(self.site, self.bel)


class CellInstance():
    """ Object to hold a cell instance. """

    def __init__(self, cell, name, ports):
        self.cell = cell
        self.name = name
        self.ports = ports

    def __repr__(self):
        return 'CellInstance({}, {}, {})'.format(
            repr(self.cell), repr(self.name), repr(self.ports))


class Constraints():
    """ Class to parse constraints and generate SAT problem expressing the constraints. """

    def __init__(self):
        self.tags = {}
        self.routed_tags = {}
        self.cells = {}

    def add_tag(self, tag):
        assert tag.name not in self.tags
        assert tag.name not in self.routed_tags

        self.tags[tag.name] = tag

    def add_routed_tag(self, routed_tag):
        assert routed_tag.name not in self.tags
        assert routed_tag.name not in self.routed_tags

        self.routed_tags[routed_tag.name] = routed_tag

    def read_constraints(self, constraints):
        """ Read constraints from constraints YAML object. """
        self.tags = {}
        self.routed_tags = {}
        self.cells = {}

        # Read tags from constraint file.
        for tag in constraints.tags:
            matchers = []

            which = tag.which()
            if which == 'siteTypes':
                for site_type in tag.siteTypes:
                    matchers.append(SiteTypeMatcher(str(site_type)))
            elif which == 'tileTypes':
                for tile_type in tag.tileTypes:
                    matchers.append(TileTypeMatcher(str(tile_type)))

            states = []
            for state in tag.states:
                states.append(str(state.state))

            self.add_tag(Tag(tag.tag, states, tag.default, matchers))

        # Read routed_tags from constraint file.
        for tag in constraints.routedTags:
            bel_pins = []
            for bel_pin in tag.belPins:
                bel_pins.append(BelPin(str(bel_pin.pin), str(bel_pin.tag)))

            self.add_routed_tag(
                RoutedTag(str(tag.routedTag), str(tag.routingBel), bel_pins))

        # Read cell constraints from constraint file.
        for cell_constraint in constraints.cellConstraints:
            if cell_constraint.which() == 'cell':
                cells = [cell_constraint.cell]
            else:
                cells = cell_constraint.cells
            for cell in cells:
                if cell not in self.cells:
                    self.cells[cell] = CellConstraints(cell)

                for location in cell_constraint.locations:
                    matchers = []

                    bel = location.bel
                    bel_which = bel.which()
                    if bel_which == 'anyBel':
                        for site_type in location.siteTypes:
                            matchers.append(SiteTypeMatcher(str(site_type)))
                    elif bel_which == 'name':
                        for site_type in location.siteTypes:
                            matchers.append(
                                BelMatcher(str(site_type), str(bel.name)))
                    elif bel_which == 'bels':
                        for site_type in location.siteTypes:
                            for bel_name in bel.bels:
                                matchers.append(
                                    BelMatcher(str(site_type), str(bel_name)))
                    else:
                        assert False, bel_which

                    which = location.which()
                    if which == 'implies':
                        for implies in location.implies:
                            port = None
                            implies_which = implies.which()
                            if implies_which == "tag":
                                tag = implies.tag
                            elif implies_which == 'RoutedTag':
                                tag = implies.routedTag.tag
                                port = str(implies.routedTag.port)

                            state = str(implies.state)
                            implies = ImpliesConstraint(
                                str(tag), state, matchers, port)
                            self.cells[cell].constraints.append(implies)
                    elif which == 'requires':
                        for requires in location.requires:
                            port = None
                            requires_which = requires.which()
                            if requires_which == "tag":
                                tag = requires.tag
                            elif requires_which == 'RoutedTag':
                                tag = requires.routedTag.tag
                                port = str(requires.routedTag.port)

                            states = [str(state) for state in requires.states]
                            self.cells[cell].constraints.append(
                                RequiresConstraint(
                                    str(tag), states, matchers, port))

        self.check_constraints()

    def check_constraints(self):
        """ Verify constraint consistency.

        Checks that:
         - Ensure that tag and routed_tag names are unique.
         - Ensure that routed tags reference a tag.
         - Ensure all cell constraints reference either a tag or routed_tag.

        """
        assert len(self.tags.keys() | self.routed_tags.keys()) == (
            len(self.tags) + len(self.routed_tags))

        for routing_tag in self.routed_tags.values():
            for bel_pin in routing_tag.bel_pins:
                assert bel_pin.tag in self.tags or bel_pin.tag in self.routed_tags

        for cell, constraints in self.cells.items():
            for constraint in constraints.constraints:
                if constraint.tag in self.routed_tags:
                    assert constraint.port is not None
                else:
                    assert constraint.tag in self.tags
                    assert constraint.port is None

    def yield_tags_at_placement(self, placement):
        for tag in self.tags.values():
            tag_prefix = tag.prefix(placement)
            if tag_prefix is not None:
                tag_prefix = tag_prefix + '.' + tag.name

                yield tag_prefix, tag

        for tag in self.routed_tags.values():
            tag_prefix = tag.prefix(placement)
            if tag_prefix is not None:
                tag_prefix = tag_prefix + '.' + tag.name

                yield tag_prefix, tag
        pass

    def yield_constraints_for_cell_type_at_placement(self, cell_type,
                                                     placement):
        cell_constraint = self.cells.get(cell_type, None)
        if cell_constraint is not None:
            for constraint in cell_constraint.for_placement(placement):
                tag = constraint.tag_for(self.tags, placement)
                yield tag, constraint

    def build_sat(self, available_placements, available_cells,
                  placement_oracle):
        """ Build a SAT problem given the placements, cells, and placement_oracle."""
        all_tags = {}

        # Emit tags and routed tags for all available placements.
        for placement in available_placements:
            for tag_prefix, tag in self.yield_tags_at_placement(placement):
                if tag_prefix in all_tags:
                    assert all_tags[tag_prefix] is tag

                all_tags[tag_prefix] = tag

        # TODO: Placements need to include routed tag stuff if present.
        # The current implementation doesn't account for routed tags at all.
        cell_to_placements = {}
        cell_name_to_cell_type = {}
        placement_to_cells = {}
        placement_to_placement_obj = {}

        # Build cell to placements and placement to cells sets.
        for cell in available_cells:
            assert cell.name not in cell_to_placements
            assert cell.name not in cell_name_to_cell_type
            cell_name_to_cell_type[cell.name] = cell.cell
            cell_to_placements[cell.name] = set()

            matchers = placement_oracle.matchers_for_cell(cell.cell)
            for placement in available_placements:
                if any(matcher.match(placement) for matcher in matchers):
                    bel_prefix = placement.bel_prefix()
                    cell_to_placements[cell.name].add(bel_prefix)

                    if bel_prefix not in placement_to_cells:
                        placement_to_cells[bel_prefix] = set()

                    placement_to_cells[bel_prefix].add(cell.name)

                    if bel_prefix in placement_to_placement_obj:
                        assert placement_to_placement_obj[
                            bel_prefix] is placement
                    else:
                        placement_to_placement_obj[bel_prefix] = placement

        del cell

        # Create state group for each tag to ensure that each tag can have 1
        # of the valid values.
        state_groups = {}
        for tag_prefix, tag in all_tags.items():
            assert tag_prefix not in state_groups

            state_group = ExclusiveStateGroup(tag_prefix, tag.default)
            for state in tag.states:
                state_group.add_state(state)

            state_groups[tag_prefix] = state_group

        # Create a state group that a cell can have 1 placement.
        for cell_name, placements in cell_to_placements.items():
            if len(placements) == 0:
                raise RuntimeError('Cell {} has no valid possible placements!'.
                                   format(cell_name))

            state_group = ExclusiveStateGroup(cell_name, default=None)
            for placement in placements:
                state_group.add_state(placement)

            assert cell_name not in state_groups
            state_groups[cell_name] = state_group

        # Create a state group that a placement can have 1 cell.
        for placement, cells in placement_to_cells.items():
            state_group = ExclusiveStateGroup(placement, default=None)
            for cell_name in cells:
                state_group.add_state(cell_name)

            state_groups[placement] = state_group

        solver = Solver()

        for state_group in state_groups.values():
            solver.add_state_group(state_group)

        for cell_name, placements in cell_to_placements.items():
            # Get constraints for cell.
            cell_type = cell_name_to_cell_type[cell_name]
            cell_constraint = self.cells.get(cell_type, None)

            # Make sure solver picks a placement for each cell
            for clause in state_groups[cell_name].select_one():
                solver.add_clause(clause)

            for placement_str in placements:
                placement = placement_to_placement_obj[placement_str]
                # When a cell is placed, also imply that the placement has a cell.
                when_cell_is_placed = state_groups[cell_name].assert_state(
                    placement_str)
                for clause in state_groups[placement_str].implies_clause(
                        when_cell_is_placed, cell_name):
                    solver.add_clause(clause)

                # When a placement has a cell, also imply that the cell has been placed.
                when_placement_has_cell = state_groups[
                    placement_str].assert_state(cell_name)
                for clause in state_groups[cell_name].implies_clause(
                        when_placement_has_cell, placement_str):
                    solver.add_clause(clause)

                # When a cell is placed, apply any constraints as needed.
                if cell_constraint is not None:
                    for constraint in cell_constraint.for_placement(placement):
                        state_group = state_groups[constraint.tag_for(
                            self.tags, placement)]
                        for clause in constraint.clauses_for(
                                when_cell_is_placed, state_group):
                            solver.add_clause(clause)

        return solver
