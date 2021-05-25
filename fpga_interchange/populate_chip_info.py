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

from fpga_interchange.chip_info import ChipInfo, BelInfo, TileTypeInfo, \
        TileWireInfo, BelPort, PipInfo, TileInstInfo, SiteInstInfo, NodeInfo, \
        TileWireRef, CellBelMap, ParameterPins, CellBelPin, ConstraintTag, \
        CellConstraint, ConstraintType, Package, PackagePin, LutCell, \
        LutElement, LutBel, CellParameter, DefaultCellConnections, DefaultCellConnection, \
        WireType, Macro, MacroNet, MacroPortInst, MacroCellInst, MacroExpansion, MacroParamMapRule, MacroParamRuleType, MacroParameter, GlobalCell, GlobalCellPin

from fpga_interchange.constraints.model import Tag, Placement, \
        ImpliesConstraint, RequiresConstraint
from fpga_interchange.constraint_generator import ConstraintPrototype
from fpga_interchange.device_resources import convert_wire_category
from fpga_interchange.nextpnr import PortType


class FlattenedWireType(Enum):
    TILE_WIRE = 0
    SITE_WIRE = 1


class FlattenedPipType(Enum):
    TILE_PIP = 0
    SITE_PIP = 1
    SITE_PIN = 2


class BelCategory(Enum):
    LOGIC = 0
    ROUTING = 1
    SITE_PORT = 2


def direction_to_type(direction):
    if direction == 'input':
        return PortType.PORT_IN
    elif direction == 'output':
        return PortType.PORT_OUT
    else:
        assert direction == 'inout'
        return PortType.PORT_INOUT


BelPin = namedtuple('BelPin', 'port type wire')


class FlattenedBel():
    def __init__(self, name, type, site_index, bel_index, bel_category,
                 lut_element):
        self.name = name
        self.type = type
        self.site_index = site_index
        self.bel_index = bel_index
        self.bel_category = bel_category
        self.ports = []
        self.non_inverting_pin = -1
        self.inverting_pin = -1

        self.valid_cells = set()
        self.lut_element = lut_element

    def add_port(self, device, bel_pin, wire_index):
        self.ports.append(
            BelPin(
                port=device.strs[bel_pin.name],
                type=direction_to_type(bel_pin.dir),
                wire=wire_index))


# Object that represents a flattened wire.
class FlattenedWire():
    def __init__(self, type, name, wire_index, site_index):
        self.type = type
        self.name = name
        self.wire_index = wire_index
        self.site_index = site_index

        self.bel_pins = []
        self.pips_uphill = []
        self.pips_downhill = []


class FlattenedPip(
        namedtuple(
            'FlattenedPip',
            'type src_index dst_index site_index pip_index pseudo_cell_wires')
):
    pass


class FlattenedSite(
        namedtuple(
            'FlattenedSite',
            'site_in_type_index site_type_index site_type site_type_name site_variant bel_to_bel_index bel_pin_to_site_wire_index bel_pin_index_to_bel_index'
        )):
    pass


def emit_constraints(tile_type, tile_constraints, cell_bel_mapper):
    flat_tag_indicies = {}
    flat_tag_state_indicies = {}

    for idx, (tag_prefix, tag_data) in enumerate(
            sorted(tile_constraints.tags.items())):
        flat_tag_indicies[tag_prefix] = idx
        flat_tag_state_indicies[tag_prefix] = {}

        tag = ConstraintTag()
        tag.tag_prefix = tag_prefix
        tag.default_state = tag_data.default
        tag.states = sorted(tag_data.states)

        for idx, state in enumerate(tag.states):
            flat_tag_state_indicies[tag_prefix][state] = idx

        tile_type.tags.append(tag)

    for (cell_type, site_index, site_type,
         bel), constraints in tile_constraints.bel_cell_constraints.items():
        idx = cell_bel_mapper.get_cell_bel_map_index(
            cell_type, tile_type.name, site_index, site_type, bel)

        outs = []
        for tag_prefix, constraint in constraints:
            out = CellConstraint()
            out.tag = flat_tag_indicies[tag_prefix]

            if isinstance(constraint, ImpliesConstraint):
                out.constraint_type = ConstraintType.TAG_IMPLIES
                out.states.append(
                    flat_tag_state_indicies[tag_prefix][constraint.state])
            elif isinstance(constraint, RequiresConstraint):
                out.constraint_type = ConstraintType.TAG_REQUIRES
                for state in constraint.states:
                    out.states.append(
                        flat_tag_state_indicies[tag_prefix][state])
            else:
                assert False, type(constraint)

            outs.append(out)

        cell_bel_mapper.cell_to_bel_constraints[idx] = outs


class LutElementsEmitter():
    def __init__(self, luts):
        self.luts = luts

    def emit(self, lut_elements):
        output_map = {}

        for lut in self.luts:
            lut_element_idx = len(lut_elements)
            lut_element = LutElement(lut_element_idx)
            lut_elements.append(lut_element)

            lut_element.width = lut.width

            for bel in lut.bels:
                lut_bel = LutBel()
                lut_element.lut_bels.append(lut_bel)

                lut_bel.name = bel.name
                for pin in bel.inputPins:
                    lut_bel.pins.append(pin)

                lut_bel.out_pin = bel.outputPin

                assert bel.lowBit < lut.width
                assert bel.highBit < lut.width

                lut_bel.low_bit = bel.lowBit
                lut_bel.high_bit = bel.highBit

                assert bel.name not in output_map, (bel.name, )
                output_map[bel.name] = lut_element_idx

        return output_map


class FlattenedTileType():
    def __init__(self, device, tile_type_index, tile_type, cell_bel_mapper,
                 constraints, lut_elements, disabled_routethrus):
        self.tile_type_name = device.strs[tile_type.name]
        self.tile_type = tile_type

        self.tile_constraints = ConstraintPrototype()

        self.sites = []
        self.bels = []
        self.bel_index_remap = {}
        self.wires = []

        self.pips = []

        self.lut_elements = []
        self.lut_elements_map = {}

        # Add tile wires
        self.tile_wire_to_wire_in_tile_index = {}
        for wire_in_tile_index, wire in enumerate(tile_type.wires):
            name = device.strs[wire]
            self.tile_wire_to_wire_in_tile_index[name] = wire_in_tile_index

            flat_wire = FlattenedWire(
                type=FlattenedWireType.TILE_WIRE,
                name=name,
                wire_index=wire_in_tile_index,
                site_index=None)
            self.add_wire(flat_wire)

        # Add pips, collecting pseudo_pips for later processing.
        pseudo_pips = []
        for idx, pip in enumerate(tile_type.pips):
            is_pseudo_cell = pip.which() == 'pseudoCells'
            if is_pseudo_cell and any(
                (device.strs[pcell.bel] in disabled_routethrus)
                    for pcell in pip.pseudoCells):
                # Skip pseudo pips through disabled cells
                continue

            pip_index = self.add_tile_pip(idx, pip.wire0, pip.wire1)

            if is_pseudo_cell:
                pseudo_pips.append((pip_index, pip))

            if not pip.directional:
                # Pseudo pips should not be bidirectional!
                assert not is_pseudo_cell

                self.add_tile_pip(idx, pip.wire1, pip.wire0)

        # Add all site variants
        for site_in_type_index, site_type_in_tile_type in enumerate(
                tile_type.siteTypes):
            site_type_index = site_type_in_tile_type.primaryType
            site_variant = -1
            primary_site_type = device.device_resource_capnp.siteTypeList[
                site_type_index]

            self.add_site_type(device, site_type_in_tile_type,
                               site_in_type_index, site_type_index,
                               site_variant, cell_bel_mapper, lut_elements)

            for site_variant, (alt_site_type_index, _) in enumerate(
                    zip(primary_site_type.altSiteTypes,
                        site_type_in_tile_type.altPinsToPrimaryPins)):
                self.add_site_type(device, site_type_in_tile_type,
                                   site_in_type_index, alt_site_type_index,
                                   site_variant, cell_bel_mapper, lut_elements,
                                   primary_site_type)

        # Now that sites have been emitted, populate pseudo_pips data.
        #
        # FIXME: This data is likely incomplete.  We need a cell type and cell
        # pin -> bel pin as well to have enough information.
        for pip_index, pip in pseudo_pips:
            flat_pip = self.pips[pip_index]
            pseudo_cell_wires = set()
            pseudo_cell_pins = {}
            pseudo_cell_pins_needed = set()
            assert pip.which() == 'pseudoCells'
            for pseudo_cell in pip.pseudoCells:
                bel_name = device.strs[pseudo_cell.bel]
                if bel_name not in pseudo_cell_pins:
                    pseudo_cell_pins[bel_name] = set()

                for pin in pseudo_cell.pins:
                    pin_name = device.strs[pin]
                    pseudo_cell_pins[bel_name].add(pin_name)

                    # Build list of expected BEL pin matches
                    pseudo_cell_pins_needed.add((bel_name, pin_name))

            # Find all sites that this pseudo pip intersects with
            sites = set()
            for other_pip in self.pips:
                if other_pip.type != FlattenedPipType.SITE_PIN:
                    continue

                if flat_pip.src_index == other_pip.src_index:
                    sites.add(other_pip.site_index)

                if flat_pip.dst_index == other_pip.dst_index:
                    sites.add(other_pip.site_index)

            for bel in self.bels:
                # This bel isn't in a site that this pseudo pip uses.
                if bel.site_index not in sites:
                    continue

                if bel.name in pseudo_cell_pins:
                    pins = pseudo_cell_pins[bel.name]

                    for port in bel.ports:
                        if port.port in pins:
                            pseudo_cell_pins_needed.discard((bel.name,
                                                             port.port))

                            if port.type == PortType.PORT_OUT:
                                # Only record wires driven by BEL pin outputs.
                                # BEL pin inputs do not consume the wire.
                                if port.wire != -1:
                                    pseudo_cell_wires.add(port.wire)

            # Make sure every BEL pin from the database matches at least 1
            # instance (possibly more!).
            assert len(pseudo_cell_pins_needed) == 0

            self.pips[pip_index].pseudo_cell_wires.clear()
            self.pips[pip_index].pseudo_cell_wires.extend(
                sorted(pseudo_cell_wires))

        self.remap_bel_indicies()
        self.generate_constraints(constraints)

    def get_lut_element_for_bel(self, lut_elements, site_type_name, site_index,
                                bel_name):
        if site_type_name not in lut_elements:
            return -1

        if site_index not in self.lut_elements_map:
            self.lut_elements_map[site_index] = lut_elements[
                site_type_name].emit(self.lut_elements)

        return self.lut_elements_map[site_index].get(bel_name, -1)

    def generate_constraints(self, constraints):
        tags_for_tile_type = {}
        available_placements = []

        sites_in_tile_type = {}
        for site_index, site in enumerate(self.sites):
            if site.site_in_type_index not in sites_in_tile_type:
                sites_in_tile_type[site.site_in_type_index] = []

            sites_in_tile_type[site.site_in_type_index].append(site_index)

        # Create tag to ensure that each site in the tile only has 1 type.
        for site, possible_sites in sites_in_tile_type.items():
            site_types = []
            for site_index in possible_sites:
                site_types.append(self.sites[site_index].site_type_name)

            # Make sure there are no duplicate site types!
            assert len(site_types) == len(set(site_types))

            tag_prefix = 'type_of_site{:03d}'.format(site)
            assert tag_prefix not in tags_for_tile_type
            tags_for_tile_type[tag_prefix] = Tag(
                name='TypeOfSite{}'.format(site),
                states=site_types,
                default=site_types[0],
                matchers=[])
            self.tile_constraints.add_tag(tag_prefix,
                                          tags_for_tile_type[tag_prefix])

        for bel in self.bels:
            site = self.sites[bel.site_index]
            placement = Placement(
                tile=self.tile_type_name,
                site='site{}_{}'.format(site.site_in_type_index,
                                        site.site_type_name),
                tile_type=self.tile_type_name,
                site_type=site.site_type_name,
                bel=bel.name)
            available_placements.append(placement)

            for tag_prefix, tag in constraints.yield_tags_at_placement(
                    placement):
                if tag_prefix in tags_for_tile_type:
                    assert tags_for_tile_type[tag_prefix] is tag
                    continue
                else:
                    tags_for_tile_type[tag_prefix] = tag
                    self.tile_constraints.add_tag(
                        tag_prefix, tags_for_tile_type[tag_prefix])

            for cell_type in bel.valid_cells:
                # When any valid cell type is placed here, make sure that
                # the corrisponding TypeOfSite tag is implied.
                self.tile_constraints.add_cell_placement_constraint(
                    cell_type=cell_type,
                    site_index=bel.site_index,
                    site_type=site.site_type_name,
                    bel=bel.name,
                    tag='type_of_site{:03d}'.format(
                        self.sites[bel.site_index].site_in_type_index),
                    constraint=ImpliesConstraint(
                        tag=None,
                        state=site.site_type_name,
                        matchers=None,
                        port=None))

                for tag, constraint in constraints.yield_constraints_for_cell_type_at_placement(
                        cell_type, placement):
                    self.tile_constraints.add_cell_placement_constraint(
                        cell_type=cell_type,
                        site_index=bel.site_index,
                        site_type=site.site_type_name,
                        bel=bel.name,
                        tag=tag,
                        constraint=constraint)

    def add_wire(self, wire):
        wire_index = len(self.wires)
        self.wires.append(wire)

        return wire_index

    def add_pip_common(self, flat_pip):
        pip_index = len(self.pips)

        self.pips.append(flat_pip)

        self.wires[flat_pip.src_index].pips_downhill.append(pip_index)
        self.wires[flat_pip.dst_index].pips_uphill.append(pip_index)

        return pip_index

    def add_tile_pip(self, tile_pip_index, src_wire, dst_wire):
        assert self.wires[src_wire].type == FlattenedWireType.TILE_WIRE
        assert self.wires[dst_wire].type == FlattenedWireType.TILE_WIRE

        flat_pip = FlattenedPip(
            type=FlattenedPipType.TILE_PIP,
            src_index=src_wire,
            dst_index=dst_wire,
            site_index=None,
            pip_index=tile_pip_index,
            pseudo_cell_wires=[])

        return self.add_pip_common(flat_pip)

    def add_site_type(self,
                      device,
                      site_type_in_tile_type,
                      site_in_type_index,
                      site_type_index,
                      site_variant,
                      cell_bel_mapper,
                      lut_elements,
                      primary_site_type=None):
        if site_variant == -1:
            assert primary_site_type is None
        else:
            assert primary_site_type is not None

        site_index = len(self.sites)

        bel_to_bel_index = {}
        bel_pin_to_site_wire_index = {}
        bel_pin_index_to_bel_index = {}

        site_type = device.device_resource_capnp.siteTypeList[site_type_index]
        site_type_name = device.strs[site_type.name]

        self.sites.append(
            FlattenedSite(
                site_in_type_index=site_in_type_index,
                site_type_index=site_type_index,
                site_type=site_type,
                site_type_name=site_type_name,
                site_variant=site_variant,
                bel_to_bel_index=bel_to_bel_index,
                bel_pin_to_site_wire_index=bel_pin_to_site_wire_index,
                bel_pin_index_to_bel_index=bel_pin_index_to_bel_index))

        # Add site wires
        for idx, site_wire in enumerate(site_type.siteWires):
            wire_name = device.strs[site_wire.name]
            flat_wire = FlattenedWire(
                type=FlattenedWireType.SITE_WIRE,
                name=wire_name,
                wire_index=idx,
                site_index=site_index)

            site_wire_index = self.add_wire(flat_wire)
            for pin in site_wire.pins:
                assert pin not in bel_pin_to_site_wire_index
                bel_pin_to_site_wire_index[pin] = site_wire_index

        # Add BELs
        for bel_idx, bel in enumerate(site_type.bels):
            if bel.category == 'logic':
                bel_category = BelCategory.LOGIC
            elif bel.category == 'routing':
                bel_category = BelCategory.ROUTING
            else:
                assert bel.category == 'sitePort', bel.category
                bel_category = BelCategory.SITE_PORT

            flat_bel = FlattenedBel(
                name=device.strs[bel.name],
                type=device.strs[bel.type],
                site_index=site_index,
                bel_index=bel_idx,
                bel_category=bel_category,
                lut_element=self.get_lut_element_for_bel(
                    lut_elements=lut_elements,
                    site_type_name=site_type_name,
                    site_index=site_index,
                    bel_name=device.strs[bel.name],
                ))
            bel_index = len(self.bels)
            bel_to_bel_index[bel_idx] = bel_index
            self.bels.append(flat_bel)

            bel_key = site_type_name, flat_bel.name
            for cell in cell_bel_mapper.get_cells():
                if bel_key in cell_bel_mapper.bels_for_cell(cell):
                    flat_bel.valid_cells.add(cell)

            for pin_idx, pin in enumerate(bel.pins):
                assert pin not in bel_pin_index_to_bel_index
                bel_pin_index_to_bel_index[pin] = bel_idx, pin_idx

                bel_pin = site_type.belPins[pin]
                wire_idx = bel_pin_to_site_wire_index.get(pin, -1)
                flat_bel.add_port(device, bel_pin, wire_idx)
                if wire_idx != -1:
                    self.wires[wire_idx].bel_pins.append(
                        (bel_index, device.strs[bel_pin.name]))

            # If this BEL is a local inverter, mark which BEL port is the
            # inverting vs non-inverting input.
            if bel.which() == 'inverting':
                inverting = bel.inverting

                _, flat_pin_idx = bel_pin_index_to_bel_index[inverting.
                                                             nonInvertingPin]
                flat_bel.non_inverting_pin = flat_pin_idx

                _, flat_pin_idx = bel_pin_index_to_bel_index[inverting.
                                                             invertingPin]
                flat_bel.inverting_pin = flat_pin_idx

        # Add site pips
        for idx, site_pip in enumerate(site_type.sitePIPs):
            src_bel_pin = site_pip.inpin
            bel_idx, src_pin_idx = bel_pin_index_to_bel_index[src_bel_pin]
            src_site_wire_idx = bel_pin_to_site_wire_index[src_bel_pin]

            dst_bel_pin = site_pip.outpin
            dst_site_wire_idx = bel_pin_to_site_wire_index[dst_bel_pin]

            self.add_site_pip(src_site_wire_idx, dst_site_wire_idx, site_index,
                              idx)

        # Add site pins
        for idx, site_pin in enumerate(site_type.pins):
            # This site pin isn't connected in this site type, skip creating
            # the edge.
            if site_pin.belpin not in bel_pin_to_site_wire_index:
                continue

            site_wire = bel_pin_to_site_wire_index[site_pin.belpin]

            if site_variant != -1:
                # This is an alternative site, map to primary pin first
                parent_pins = site_type_in_tile_type.altPinsToPrimaryPins[
                    site_variant]
                primary_idx = parent_pins.pins[idx]
            else:
                # This is the primary site, directly lookup site tile wire.
                primary_idx = idx

            tile_wire_name = device.strs[site_type_in_tile_type.
                                         primaryPinsToTileWires[primary_idx]]
            tile_wire = self.tile_wire_to_wire_in_tile_index[tile_wire_name]

            if site_pin.dir == 'input':
                # Input site pins connect tile wires to site wires
                src_wire = tile_wire
                dst_wire = site_wire
            else:
                assert site_pin.dir == 'output'
                # Output site pins connect site wires to tile wires
                src_wire = site_wire
                dst_wire = tile_wire

            self.add_site_pin(src_wire, dst_wire, site_index, idx)

    def add_site_pip(self, src_wire, dst_wire, site_index, site_pip_index):
        assert self.wires[src_wire].type == FlattenedWireType.SITE_WIRE
        assert self.wires[dst_wire].type == FlattenedWireType.SITE_WIRE

        flat_pip = FlattenedPip(
            type=FlattenedPipType.SITE_PIP,
            src_index=src_wire,
            dst_index=dst_wire,
            site_index=site_index,
            pip_index=site_pip_index,
            pseudo_cell_wires=[])

        return self.add_pip_common(flat_pip)

    def add_site_pin(self, src_wire, dst_wire, site_index, site_pin_index):
        if self.wires[src_wire].type == FlattenedWireType.SITE_WIRE:
            assert self.wires[dst_wire].type == FlattenedWireType.TILE_WIRE
        else:
            assert self.wires[src_wire].type == FlattenedWireType.TILE_WIRE
            assert self.wires[dst_wire].type == FlattenedWireType.SITE_WIRE

        flat_pip = FlattenedPip(
            type=FlattenedPipType.SITE_PIN,
            src_index=src_wire,
            dst_index=dst_wire,
            site_index=site_index,
            pip_index=site_pin_index,
            pseudo_cell_wires=[])

        return self.add_pip_common(flat_pip)

    def remap_bel_indicies(self):
        # Put logic BELs first before routing and site ports.
        self.bel_index_remap = {}
        self.bel_output_map = {}
        for output_bel_idx, (bel_idx, _) in enumerate(
                sorted(
                    enumerate(self.bels),
                    key=lambda value: (value[1].bel_category.value, value[0]))
        ):
            self.bel_index_remap[bel_idx] = output_bel_idx
            self.bel_output_map[output_bel_idx] = bel_idx

    def create_tile_type_info(self, cell_bel_mapper):
        tile_type = TileTypeInfo()
        tile_type.name = self.tile_type_name
        tile_type.lut_elements = self.lut_elements

        bels_used = set()
        for bel_index in range(len(self.bels)):
            mapped_idx = self.bel_output_map[bel_index]
            assert mapped_idx not in bels_used
            bels_used.add(mapped_idx)

            bel = self.bels[mapped_idx]
            bel_info = BelInfo()
            bel_info.name = bel.name
            bel_info.type = bel.type

            for port in bel.ports:
                bel_info.ports.append(port.port)
                bel_info.types.append(port.type.value)
                bel_info.wires.append(port.wire)

            bel_info.site = bel.site_index
            bel_info.site_variant = self.sites[bel.site_index].site_variant
            bel_info.bel_category = bel.bel_category.value
            bel_info.lut_element = bel.lut_element
            bel_info.non_inverting_pin = bel.non_inverting_pin
            bel_info.inverting_pin = bel.inverting_pin

            site_type = self.sites[bel.site_index].site_type_name

            bel_key = (site_type, bel.name)
            bel_info.bel_bucket = cell_bel_mapper.bel_to_bel_bucket(*bel_key)

            if bel.bel_category == BelCategory.LOGIC:
                # Don't need pin_map for routing / site ports.
                bel_info.pin_map = [-1 for _ in cell_bel_mapper.get_cells()]
                for idx, cell in enumerate(cell_bel_mapper.get_cells()):
                    bel_info.pin_map[
                        idx] = cell_bel_mapper.get_cell_bel_map_index(
                            cell, tile_type.name, bel.site_index, site_type,
                            bel.name)

            tile_type.bel_data.append(bel_info)

        assert len(bels_used) == len(self.bel_output_map)
        assert len(bels_used) == len(self.bel_index_remap)

        for wire in self.wires:
            wire_info = TileWireInfo()
            wire_info.name = wire.name
            wire_info.pips_uphill = wire.pips_uphill
            wire_info.pips_downhill = wire.pips_downhill

            for (bel_index, port) in wire.bel_pins:
                bel_port = BelPort()
                bel_port.bel_index = self.bel_index_remap[bel_index]
                bel_port.port = port

                wire_info.bel_pins.append(bel_port)

            if wire.site_index is not None:
                wire_info.site = wire.site_index
                wire_info.site_variant = self.sites[wire.
                                                    site_index].site_variant
            else:
                wire_info.site = -1
                wire_info.site_variant = -1

            tile_type.wire_data.append(wire_info)

        for pip in self.pips:
            pip_info = PipInfo()

            pip_info.src_index = pip.src_index
            pip_info.dst_index = pip.dst_index
            pip_info.pseudo_cell_wires = pip.pseudo_cell_wires

            if pip.site_index is not None:
                site = self.sites[pip.site_index]
                site_type = site.site_type

                pip_info.site = pip.site_index
                pip_info.site_variant = site.site_variant

                if pip.type == FlattenedPipType.SITE_PIP:
                    site_pip = site_type.sitePIPs[pip.pip_index]
                    bel_idx, pin_idx = site.bel_pin_index_to_bel_index[
                        site_pip.inpin]
                    orig_bel_index = site.bel_to_bel_index[bel_idx]
                    expected_category = self.bels[orig_bel_index].bel_category
                    assert expected_category in [
                        BelCategory.ROUTING, BelCategory.LOGIC
                    ]

                    pip_info.bel = self.bel_index_remap[orig_bel_index]
                    assert tile_type.bel_data[
                        pip_info.bel].bel_category == expected_category.value
                    pip_info.extra_data = pin_idx
                else:
                    assert pip.type == FlattenedPipType.SITE_PIN
                    site_pin = site_type.pins[pip.pip_index]
                    bel_idx, pin_idx = site.bel_pin_index_to_bel_index[
                        site_pin.belpin]
                    pip_info.bel = self.bel_index_remap[
                        site.bel_to_bel_index[bel_idx]]
                    pip_info.extra_data = pin_idx
                    assert tile_type.bel_data[
                        pip_info.
                        bel].bel_category == BelCategory.SITE_PORT.value
            else:
                assert pip.type == FlattenedPipType.TILE_PIP
                pip_info.site = -1
                pip_info.site_variant = -1

            tile_type.pip_data.append(pip_info)

        emit_constraints(tile_type, self.tile_constraints, cell_bel_mapper)

        for site in self.sites:
            tile_type.site_types.append(site.site_type_name)

        return tile_type


class CellBelMapper():
    def __init__(self, device, constids, disabled_cell_bel_maps):
        def is_cell_bel_map_disabled(cell, bel):
            for exclusion_map in disabled_cell_bel_maps:
                if exclusion_map['cell'] == cell:
                    return bel in exclusion_map['bels']

            return False

        # Emit cell names so that they are compact list.
        self.cells_in_order = []
        self.cell_names = {}
        self.bel_buckets = set()
        self.cell_to_bel_buckets = {}
        self.cell_to_bel_common_pins = {}
        self.cell_to_bel_parameter_pins = {}
        self.cell_site_bel_index = {}
        self.cell_to_bel_constraints = {}
        self.bel_to_bel_buckets = {}

        for cell_bel_map in device.device_resource_capnp.cellBelMap:
            cell_name = device.strs[cell_bel_map.cell]
            self.cells_in_order.append(cell_name)
            self.cell_names[cell_name] = constids.get_index(cell_name)

        self.min_cell_index = min(self.cell_names.values())
        self.max_cell_index = max(self.cell_names.values())

        # Make sure cell names are a compact range.
        assert (self.max_cell_index - self.min_cell_index + 1) == len(
            self.cell_names)

        # Remap cell_names as offset from min_cell_index.
        for cell_name in self.cell_names.keys():
            cell_index = self.cell_names[cell_name] - self.min_cell_index
            self.cell_names[cell_name] = cell_index
            assert self.cells_in_order[cell_index] == cell_name

        self.cell_to_bel_map = {}

        for cell_bel_map in device.device_resource_capnp.cellBelMap:
            cell_type = device.strs[cell_bel_map.cell]
            assert cell_type in self.cell_names

            bels = set()

            for common_pin in cell_bel_map.commonPins:
                pins = []
                for pin in common_pin.pins:
                    pins.append((device.strs[pin.cellPin],
                                 device.strs[pin.belPin]))

                for site_types_and_bels in common_pin.siteTypes:
                    site_type = device.strs[site_types_and_bels.siteType]
                    for bel_str_id in site_types_and_bels.bels:
                        bel = device.strs[bel_str_id]

                        if is_cell_bel_map_disabled(cell_type, bel):
                            continue

                        bels.add((site_type, bel))

                        key = (cell_type, site_type, bel)
                        assert key not in self.cell_to_bel_common_pins
                        self.cell_to_bel_common_pins[key] = pins

            for parameter_pin in cell_bel_map.parameterPins:
                pins = []
                for pin in parameter_pin.pins:
                    pins.append((device.strs[pin.cellPin],
                                 device.strs[pin.belPin]))

                for parameter in parameter_pin.parametersSiteTypes:
                    param_key = device.strs[parameter.parameter.key]
                    which = parameter.parameter.which()
                    assert which == 'textValue'
                    param_value = device.strs[parameter.parameter.textValue]

                    bel = device.strs[parameter.bel]

                    if is_cell_bel_map_disabled(cell_type, bel):
                        continue

                    site_type = device.strs[parameter.siteType]
                    bels.add((site_type, bel))

                    key = cell_type, site_type, bel
                    if key not in self.cell_to_bel_parameter_pins:
                        self.cell_to_bel_parameter_pins[key] = {}

                    assert (param_key, param_value
                            ) not in self.cell_to_bel_parameter_pins[key]
                    self.cell_to_bel_parameter_pins[key][(param_key,
                                                          param_value)] = pins

            self.cell_to_bel_map[cell_type] = bels

        self.bels = set()
        for site_type in device.device_resource_capnp.siteTypeList:
            for bel in site_type.bels:
                self.bels.add((device.strs[site_type.name],
                               device.strs[bel.name]))

    def get_cell_bel_map_index(self, cell_type, tile_type, site_index,
                               site_type, bel):
        if cell_type not in self.cell_to_bel_map:
            return -1

        if (site_type, bel) not in self.cell_to_bel_map[cell_type]:
            return -1

        key = cell_type, tile_type, site_index, site_type, bel
        if key not in self.cell_site_bel_index:
            index = len(self.cell_site_bel_index)
            self.cell_site_bel_index[key] = index

        return self.cell_site_bel_index[key]

    def make_bel_bucket(self, bel_bucket_name, cell_names):
        assert bel_bucket_name not in self.bel_buckets

        bels_in_bucket = set()
        cells_in_bucket = set(cell_names)

        while True:
            pre_loop_counts = (len(bels_in_bucket), len(cells_in_bucket))

            for cell_name in cells_in_bucket:
                bels_in_bucket |= self.cell_to_bel_map[cell_name]

            for bel in bels_in_bucket:
                for cell, bels in self.cell_to_bel_map.items():
                    if bel in bels:
                        cells_in_bucket.add(cell)

            post_loop_counts = (len(bels_in_bucket), len(cells_in_bucket))

            if pre_loop_counts == post_loop_counts:
                break

        assert bel_bucket_name not in self.bel_buckets
        self.bel_buckets.add(bel_bucket_name)

        for cell in cells_in_bucket:
            assert cell not in self.cell_to_bel_buckets, (bel_bucket_name,
                                                          cell)
            self.cell_to_bel_buckets[cell] = bel_bucket_name

        for bel in bels_in_bucket:
            self.bel_to_bel_buckets[bel] = bel_bucket_name

    def handle_remaining(self):
        remaining_cells = set(self.cell_names.keys()) - set(
            self.cell_to_bel_buckets.keys())

        for cell in sorted(remaining_cells):
            self.make_bel_bucket(cell, [cell])

        remaining_bels = set(self.bels)
        for bels in self.cell_to_bel_map.values():
            remaining_bels -= bels

        bel_bucket_name = 'UNPLACABLE_BELS'
        assert bel_bucket_name not in self.bel_buckets
        self.bel_buckets.add(bel_bucket_name)
        for site_type, bel in remaining_bels:
            self.bel_to_bel_buckets[site_type, bel] = bel_bucket_name

        bel_bucket_name = 'IOPORTS'
        assert bel_bucket_name not in self.bel_buckets
        self.bel_buckets.add(bel_bucket_name)

    def get_cells(self):
        return self.cells_in_order

    def get_cell_constids(self):
        return range(self.min_cell_index, self.max_cell_index + 1)

    def get_cell_index(self, cell_name):
        return self.cell_names[cell_name]

    def get_bel_buckets(self):
        return self.bel_buckets

    def cell_to_bel_bucket(self, cell_name):
        return self.cell_to_bel_buckets[cell_name]

    def get_bels(self):
        return self.bel_to_bel_buckets.keys()

    def bel_to_bel_bucket(self, site_type, bel):
        return self.bel_to_bel_buckets[(site_type, bel)]

    def bels_for_cell(self, cell):
        return self.cell_to_bel_map[cell]


DEBUG_BEL_BUCKETS = False


def print_bel_buckets(cell_bel_mapper):
    print('BEL buckets:')
    for bel_bucket in cell_bel_mapper.get_bel_buckets():
        print(' - {}'.format(bel_bucket))

    print('')
    print('Cell -> BEL bucket:')
    for cell in sorted(
            cell_bel_mapper.get_cells(),
            key=lambda cell: (cell_bel_mapper.cell_to_bel_bucket(cell), cell)):
        print(' - {} => {}'.format(cell,
                                   cell_bel_mapper.cell_to_bel_bucket(cell)))

    print('')
    print('BEL -> BEL bucket:')
    for site_type, bel in sorted(
            cell_bel_mapper.get_bels(),
            key=lambda key: (cell_bel_mapper.bel_to_bel_bucket(*key), *key)):
        print(' - {}/{} => {}'.format(
            site_type, bel, cell_bel_mapper.bel_to_bel_bucket(site_type, bel)))


class SyntheticType(Enum):
    SIGNAL = 1
    GND = 2
    VCC = 3


class ConstantNetworkGenerator():
    def __init__(self, device, chip_info, cell_bel_mapper):
        self.device = device
        self.chip_info = chip_info
        self.constants = chip_info.constants
        self.cell_bel_mapper = cell_bel_mapper

        self.site_type = '$CONSTANTS'
        self.site_name = '$CONSTANTS_X0Y0'
        self.tile_type_name = '$CONSTANTS'
        self.tile_name = '$CONSTANTS_X0Y0'

        self.tile_type, gnd_bel, vcc_bel = self.create_initial_bels()
        self.gnd_node_wire, self.vcc_node_wire = self.initialize_constant_network(
            self.tile_type, gnd_bel, vcc_bel)

    def create_initial_bels(self):
        """ Create initial BELs that are the global constant sources. """
        consts = self.device.get_constants()

        self.constants.gnd_cell_name = consts.GND_CELL_TYPE
        self.constants.gnd_cell_port = consts.GND_PORT

        self.constants.vcc_cell_name = consts.VCC_CELL_TYPE
        self.constants.vcc_cell_port = consts.VCC_PORT

        self.constants.gnd_bel_index = 0
        self.constants.gnd_bel_pin = self.constants.gnd_cell_port

        self.constants.vcc_bel_index = 1
        self.constants.vcc_bel_pin = self.constants.vcc_cell_port

        self.constants.gnd_net_name = consts.GND_NET
        self.constants.vcc_net_name = consts.VCC_NET

        if self.device.device_resource_capnp.constants.defaultBestConstant == 'noPreference':
            # Use ('',) instead of '' to clearly mark that we want the empty
            # string.
            self.constants.best_constant_net = ('', )
        elif self.device.device_resource_capnp.constants.defaultBestConstant == 'gnd':
            self.constants.best_constant_net = consts.GND_NET
        elif self.device.device_resource_capnp.constants.defaultBestConstant == 'vcc':
            self.constants.best_constant_net = consts.VCC_NET
        else:
            assert False, self.device.device_resource_capnp.constants.defaultBestConstant

        tile_type = TileTypeInfo()
        self.tile_type_index = len(self.chip_info.tile_types)
        self.chip_info.tile_types.append(tile_type)

        tile_type.site_types.append(self.site_type)

        self.cell_bel_mapper.cell_to_bel_map[
            self.constants.gnd_cell_name] = set(
                ((self.site_type, self.constants.gnd_cell_name), ))
        self.cell_bel_mapper.cell_to_bel_map[
            self.constants.vcc_cell_name] = set(
                ((self.site_type, self.constants.vcc_cell_name), ))

        # Create BELs to be the source of the constant networks.
        gnd_bel = BelInfo()
        gnd_bel.name = self.constants.gnd_cell_name
        gnd_bel.type = self.constants.gnd_cell_name
        gnd_bel.bel_bucket = self.cell_bel_mapper.cell_to_bel_bucket(
            self.constants.gnd_cell_name)

        gnd_bel.ports.append(self.constants.gnd_cell_port)
        gnd_bel.types.append(PortType.PORT_OUT)
        gnd_bel.wires.append(0)

        gnd_bel.site = 0
        gnd_bel.site_variant = -1
        gnd_bel.bel_category = BelCategory.LOGIC.value
        gnd_bel.synthetic = SyntheticType.GND.value

        gnd_bel.pin_map = [-1 for _ in self.cell_bel_mapper.get_cells()]
        gnd_cell_idx = self.cell_bel_mapper.get_cell_index(
            self.constants.gnd_cell_name)
        gnd_bel.pin_map[
            gnd_cell_idx] = self.cell_bel_mapper.get_cell_bel_map_index(
                cell_type=self.constants.gnd_cell_name,
                tile_type=self.tile_type_name,
                site_index=0,
                site_type=self.site_type,
                bel=gnd_bel.name)
        assert gnd_bel.pin_map[gnd_cell_idx] != -1

        assert len(tile_type.bel_data) == self.constants.gnd_bel_index
        tile_type.bel_data.append(gnd_bel)

        vcc_bel = BelInfo()
        vcc_bel.name = self.constants.vcc_cell_name
        vcc_bel.type = self.constants.vcc_cell_name
        vcc_bel.bel_bucket = self.cell_bel_mapper.cell_to_bel_bucket(
            self.constants.vcc_cell_name)

        vcc_bel.ports.append(self.constants.vcc_cell_port)
        vcc_bel.types.append(PortType.PORT_OUT)
        vcc_bel.wires.append(1)

        vcc_bel.site = 0
        vcc_bel.site_variant = -1
        vcc_bel.bel_category = BelCategory.LOGIC.value
        vcc_bel.synthetic = SyntheticType.VCC.value

        vcc_bel.pin_map = [-1 for _ in self.cell_bel_mapper.get_cells()]
        vcc_cell_idx = self.cell_bel_mapper.get_cell_index(
            self.constants.vcc_cell_name)
        vcc_bel.pin_map[
            vcc_cell_idx] = self.cell_bel_mapper.get_cell_bel_map_index(
                cell_type=self.constants.vcc_cell_name,
                tile_type=self.tile_type_name,
                site_index=0,
                site_type=self.site_type,
                bel=vcc_bel.name)
        assert vcc_bel.pin_map[vcc_cell_idx] != -1

        assert len(tile_type.bel_data) == self.constants.vcc_bel_index
        tile_type.bel_data.append(vcc_bel)

        self.cell_bel_mapper.bels.add((self.site_name, gnd_bel.name))
        self.cell_bel_mapper.bels.add((self.site_name, vcc_bel.name))

        key = (self.constants.gnd_cell_name, self.site_type, gnd_bel.name)
        self.cell_bel_mapper.cell_to_bel_common_pins[key] = ((
            self.constants.gnd_cell_port, self.constants.gnd_cell_port), )

        key = (self.constants.vcc_cell_name, self.site_type, vcc_bel.name)
        self.cell_bel_mapper.cell_to_bel_common_pins[key] = ((
            self.constants.vcc_cell_port, self.constants.vcc_cell_port), )

        tile_type.name = self.tile_type_name

        return tile_type, gnd_bel, vcc_bel

    def initialize_constant_network(self, tile_type, gnd_bel, vcc_bel):
        """ Create site wiring to connect GND/VCC source to a node.

        Create site pins (as if it were a real site).
        """

        gnd_wire = TileWireInfo()
        assert len(tile_type.wire_data) == gnd_bel.wires[0]
        tile_type.wire_data.append(gnd_wire)

        gnd_wire.name = '$GND_SOURCE'
        gnd_wire.site = 0
        gnd_wire.site_variant = -1

        gnd_wire_bel_port = BelPort()
        gnd_wire_bel_port.bel_index = self.constants.gnd_bel_index
        gnd_wire_bel_port.port = gnd_bel.ports[0]

        gnd_wire.bel_pins.append(gnd_wire_bel_port)

        vcc_wire = TileWireInfo()
        assert len(tile_type.wire_data) == vcc_bel.wires[0]
        tile_type.wire_data.append(vcc_wire)

        vcc_wire.name = '$VCC_SOURCE'
        vcc_wire.site = 0
        vcc_wire.site_variant = -1

        vcc_wire_bel_port = BelPort()
        vcc_wire_bel_port.bel_index = self.constants.vcc_bel_index
        vcc_wire_bel_port.port = vcc_bel.ports[0]

        vcc_wire.bel_pins.append(vcc_wire_bel_port)

        # Construct site port for GND_SOURCE.

        # Create the pip that is the edge between the site and the first wire in
        # the graph
        gnd_site_port = PipInfo()
        gnd_site_port_pip_idx = len(tile_type.pip_data)
        tile_type.pip_data.append(gnd_site_port)

        # Populate the site port edge information
        gnd_site_port.site = 0
        gnd_site_port.site_variant = -1
        gnd_site_port.extra_data = 0
        gnd_site_port.src_index = gnd_bel.wires[0]

        # Create the first wire for the ground graph.
        gnd_site_port.dst_index = len(tile_type.wire_data)
        gnd_node_wire = TileWireInfo()
        tile_type.wire_data.append(gnd_node_wire)

        # Update the wires upstream and downstream from the pip.
        gnd_wire.pips_downhill.append(gnd_site_port_pip_idx)
        gnd_node_wire.pips_uphill.append(gnd_site_port_pip_idx)

        # Finish populating the first wire in the graph.
        gnd_node_wire.name = '$GND_NODE'
        gnd_node_wire.site = -1

        # Create the site port BEL for the site port pip.
        gnd_site_port.bel = len(tile_type.bel_data)

        gnd_site_port_bel = BelInfo()
        tile_type.bel_data.append(gnd_site_port_bel)

        gnd_site_port_bel.name = '$GND'
        gnd_site_port_bel.type = 'NA'
        gnd_site_port_bel.bel_bucket = 'UNPLACABLE_BELS'
        gnd_site_port_bel.ports.append(gnd_site_port_bel.name)
        gnd_site_port_bel.types.append(PortType.PORT_IN.value)
        gnd_site_port_bel.wires.append(gnd_bel.wires[0])
        gnd_site_port_bel.site = 0
        gnd_site_port_bel.site_variant = -1
        gnd_site_port_bel.bel_category = BelCategory.SITE_PORT.value
        gnd_site_port_bel.synthetic = SyntheticType.GND.value

        # Attach the site port to the site wire.
        gnd_site_port_bel_port = BelPort()
        gnd_site_port_bel_port.bel_index = gnd_site_port.bel
        gnd_site_port_bel_port.port = gnd_site_port_bel.name
        gnd_wire.bel_pins.append(gnd_site_port_bel_port)

        # Construct site port for VCC_SOURCE.

        # Create the pip that is the edge between the site and the first wire in
        # the graph
        vcc_site_port = PipInfo()
        vcc_site_port_pip_idx = len(tile_type.pip_data)
        tile_type.pip_data.append(vcc_site_port)

        # Populate the site port edge information
        vcc_site_port.site = 0
        vcc_site_port.site_variant = -1
        vcc_site_port.extra_data = 0
        vcc_site_port.src_index = vcc_bel.wires[0]

        # Create the first wire for the ground graph.
        vcc_site_port.dst_index = len(tile_type.wire_data)
        vcc_node_wire = TileWireInfo()
        tile_type.wire_data.append(vcc_node_wire)

        # Update the wires upstream and downstream from the pip.
        vcc_wire.pips_downhill.append(vcc_site_port_pip_idx)
        vcc_node_wire.pips_uphill.append(vcc_site_port_pip_idx)

        # Finish populating the first wire in the graph.
        vcc_node_wire.name = '$VCC_NODE'
        vcc_node_wire.site = -1

        # Create the site port BEL for the site port pip.
        vcc_site_port.bel = len(tile_type.bel_data)

        vcc_site_port_bel = BelInfo()
        tile_type.bel_data.append(vcc_site_port_bel)

        vcc_site_port_bel.name = '$VCC'
        vcc_site_port_bel.type = 'NA'
        vcc_site_port_bel.bel_bucket = 'UNPLACABLE_BELS'
        vcc_site_port_bel.ports.append(vcc_site_port_bel.name)
        vcc_site_port_bel.types.append(PortType.PORT_IN.value)
        vcc_site_port_bel.wires.append(vcc_bel.wires[0])
        vcc_site_port_bel.site = 0
        vcc_site_port_bel.site_variant = -1
        vcc_site_port_bel.bel_category = BelCategory.SITE_PORT.value
        vcc_site_port_bel.synthetic = SyntheticType.VCC.value

        # Attach the site port to the site wire.
        vcc_site_port_bel_port = BelPort()
        vcc_site_port_bel_port.bel_index = vcc_site_port.bel
        vcc_site_port_bel_port.port = vcc_site_port_bel.name
        vcc_wire.bel_pins.append(vcc_site_port_bel_port)

        return (gnd_site_port.dst_index, vcc_site_port.dst_index)

    def populate_constant_network(self):
        """ Create nodes that reach every tile that needs the constant network.

        Create a tile local wire for each tile that has a constant source.
        Connect the constant node to that local wire.  Then create an edge
        from that local wire to the specific source.

        The reason for this is to allow the router to intellegently search the
        constant network.

        """
        device = self.device

        tile_idx = 0

        # Overwrite tile at 0,0 assuming that it is a NULL tile.
        null_tile_type = self.chip_info.tile_types[self.chip_info.
                                                   tiles[tile_idx].type]
        # FIXME: Make these checks more robust and not dependant on
        #        non-well-defined naming conventions.
        assert null_tile_type.name == 'NULL', null_tile_type.name
        contains_dummy_wires = all(
            'DUMMY' in wire.name for wire in null_tile_type.wire_data)
        assert len(null_tile_type.wire_data) == 0 or contains_dummy_wires, len(
            null_tile_type.wire_data)

        self.constants.gnd_bel_tile = tile_idx
        self.constants.vcc_bel_tile = tile_idx

        self.chip_info.tiles[tile_idx].name = self.tile_name
        self.chip_info.tiles[tile_idx].type = self.tile_type_index
        self.chip_info.tiles[tile_idx].sites = [len(self.chip_info.sites)]
        site_inst = SiteInstInfo()
        self.chip_info.sites.append(site_inst)

        site_inst.name = '{}.{}'.format(self.site_name, self.site_type)
        site_inst.site_name = self.site_name
        site_inst.site_type = self.site_type

        self.chip_info.tiles[tile_idx].tile_wire_to_node = [
            -1 for _ in range(len(self.tile_type.wire_data))
        ]

        # Create nodes for the global constant network
        gnd_node_idx = len(self.chip_info.nodes)
        self.chip_info.tiles[tile_idx].tile_wire_to_node[
            self.gnd_node_wire] = gnd_node_idx
        gnd_node = NodeInfo()
        self.chip_info.nodes.append(gnd_node)
        gnd_node.name = 'gnd_node'

        gnd_node_ref = TileWireRef()
        gnd_node.tile_wires.append(gnd_node_ref)

        gnd_node_ref.tile = tile_idx
        gnd_node_ref.index = self.gnd_node_wire

        vcc_node_idx = len(self.chip_info.nodes)
        self.chip_info.tiles[tile_idx].tile_wire_to_node[
            self.vcc_node_wire] = vcc_node_idx
        vcc_node = NodeInfo()
        self.chip_info.nodes.append(vcc_node)
        vcc_node.name = 'vcc_node'

        vcc_node_ref = TileWireRef()
        vcc_node.tile_wires.append(vcc_node_ref)

        vcc_node_ref.tile = tile_idx
        vcc_node_ref.index = self.vcc_node_wire

        bel_pins_connected_to_gnd = set()
        bel_pins_connected_to_vcc = set()
        site_types_with_gnd = set()
        site_types_with_vcc = set()
        for site_source in device.device_resource_capnp.constants.siteSources:
            site_type = device.strs[site_source.siteType]
            bel = device.strs[site_source.bel]
            bel_pin = device.strs[site_source.belPin]

            if site_source.constant == 'gnd':
                site_types_with_gnd.add(site_type)
                bel_pins_connected_to_gnd.add((site_type, bel, bel_pin))
            elif site_source.constant == 'vcc':
                site_types_with_vcc.add(site_type)
                bel_pins_connected_to_vcc.add((site_type, bel, bel_pin))
            else:
                assert False, site_source.constant

        tile_types_with_gnd = set()
        tile_types_with_vcc = set()

        for tile_type_idx, tile_type in enumerate(self.chip_info.tile_types):
            if tile_type_idx == self.tile_type_index:
                continue

            tile_type_data = device.device_resource_capnp.tileTypeList[
                tile_type_idx]
            assert device.strs[tile_type_data.name] == tile_type.name

            for wire_constant in tile_type_data.constants:
                if wire_constant.constant == 'gnd':
                    tile_types_with_gnd.add(tile_type_idx)
                elif wire_constant.constant == 'vcc':
                    tile_types_with_vcc.add(tile_type_idx)
                else:
                    assert False, wire_constant.constant

            for site_in_tile_type in tile_type_data.siteTypes:
                site_type = device.device_resource_capnp.siteTypeList[
                    site_in_tile_type.primaryType]

                site_type_name = device.strs[site_type.name]
                if site_type_name in site_types_with_gnd:
                    tile_types_with_gnd.add(tile_type_idx)

                if site_type_name in site_types_with_vcc:
                    tile_types_with_vcc.add(tile_type_idx)

                for alt_site_type_idx in site_type.altSiteTypes:
                    alt_site_type = device.device_resource_capnp.siteTypeList[
                        alt_site_type_idx]

                    site_type_name = device.strs[alt_site_type.name]
                    if site_type_name in site_types_with_gnd:
                        tile_types_with_gnd.add(tile_type_idx)

                    if site_type_name in site_types_with_vcc:
                        tile_types_with_vcc.add(tile_type_idx)

        # Create gnd local wire in each type that needs it
        tile_type_gnd_wires = {}
        for tile_type_idx in tile_types_with_gnd:
            tile_type = self.chip_info.tile_types[tile_type_idx]

            gnd_wire_idx = len(tile_type.wire_data)
            gnd_wire = TileWireInfo()
            tile_type.wire_data.append(gnd_wire)

            gnd_wire.name = '$GND_WIRE'
            gnd_wire.site = -1

            tile_type_gnd_wires[tile_type_idx] = gnd_wire_idx

        # Add gnd local wire in each instance to node
        for tile_idx, tile in enumerate(self.chip_info.tiles):
            if tile.type not in tile_types_with_gnd:
                continue

            gnd_wire_idx = tile_type_gnd_wires[tile.type]
            assert gnd_wire_idx >= len(
                tile.tile_wire_to_node), (gnd_wire_idx,
                                          len(tile.tile_wire_to_node),
                                          len(tile_type.wire_data))

            while gnd_wire_idx > len(tile.tile_wire_to_node):
                tile.tile_wire_to_node.append(-1)

            tile.tile_wire_to_node.append(gnd_node_idx)

            wire_ref = TileWireRef()
            wire_ref.tile = tile_idx
            wire_ref.index = gnd_wire_idx

            gnd_node.tile_wires.append(wire_ref)

        # Create vcc local wire in each type that needs it
        tile_type_vcc_wires = {}
        for tile_type_idx in tile_types_with_vcc:
            tile_type = self.chip_info.tile_types[tile_type_idx]

            vcc_wire_idx = len(tile_type.wire_data)
            vcc_wire = TileWireInfo()
            tile_type.wire_data.append(vcc_wire)

            vcc_wire.name = '$VCC_WIRE'
            vcc_wire.site = -1

            tile_type_vcc_wires[tile_type_idx] = vcc_wire_idx

        # Add vcc local wire in each instance to node
        for tile_idx, tile in enumerate(self.chip_info.tiles):
            if tile.type not in tile_types_with_vcc:
                continue

            vcc_wire_idx = tile_type_vcc_wires[tile.type]
            assert vcc_wire_idx >= len(tile.tile_wire_to_node)

            while vcc_wire_idx > len(tile.tile_wire_to_node):
                tile.tile_wire_to_node.append(-1)

            tile.tile_wire_to_node.append(vcc_node_idx)

            wire_ref = TileWireRef()
            wire_ref.tile = tile_idx
            wire_ref.index = vcc_wire_idx

            vcc_node.tile_wires.append(wire_ref)

        for tile_type_idx in (tile_types_with_gnd | tile_types_with_vcc):
            gnd_wire_idx = tile_type_gnd_wires.get(tile_type_idx, None)
            vcc_wire_idx = tile_type_vcc_wires.get(tile_type_idx, None)

            self.connect_tile_type(tile_type_idx, gnd_wire_idx, vcc_wire_idx,
                                   bel_pins_connected_to_gnd,
                                   bel_pins_connected_to_vcc)

        # FIXME: Implement node constant sources.
        #
        # Node constant sources are rarer, and less important, so don't
        # import them right now.

    def connect_tile_type(self, tile_type_idx, gnd_wire_idx, vcc_wire_idx,
                          bel_pins_connected_to_gnd,
                          bel_pins_connected_to_vcc):
        device = self.device

        tile_type = self.chip_info.tile_types[tile_type_idx]
        tile_type_data = self.device.device_resource_capnp.tileTypeList[
            tile_type_idx]
        assert device.strs[tile_type_data.name] == tile_type.name

        gnd_site_wires = {}
        vcc_site_wires = {}

        for bel_info in tile_type.bel_data:
            site_type = tile_type.site_types[bel_info.site]
            for bel_pin_idx, bel_pin in enumerate(bel_info.ports):
                wire_idx = bel_info.wires[bel_pin_idx]

                if wire_idx == -1:
                    continue

                key = (site_type, bel_info.name, bel_pin)
                src_wire_idx = None
                if key in bel_pins_connected_to_gnd:
                    assert key not in bel_pins_connected_to_vcc

                    synthetic_type = SyntheticType.GND

                    gnd_site_wire_idx = gnd_site_wires.get(bel_info.site, None)
                    if gnd_site_wire_idx is None:
                        gnd_site_wire_idx = self.build_input_site_port(
                            tile_type_idx=tile_type_idx,
                            port_name='$GND',
                            site_wire_name='$GND_SITE_WIRE',
                            tile_wire_idx=gnd_wire_idx,
                            site=bel_info.site,
                            site_variant=bel_info.site_variant,
                            synthetic_type=synthetic_type)

                        gnd_site_wires[bel_info.site] = gnd_site_wire_idx

                    src_wire_idx = gnd_site_wire_idx
                elif key in bel_pins_connected_to_vcc:
                    assert key not in bel_pins_connected_to_gnd

                    synthetic_type = SyntheticType.VCC

                    vcc_site_wire_idx = vcc_site_wires.get(bel_info.site, None)
                    if vcc_site_wire_idx is None:
                        vcc_site_wire_idx = self.build_input_site_port(
                            tile_type_idx=tile_type_idx,
                            port_name='$VCC',
                            site_wire_name='$VCC_SITE_WIRE',
                            tile_wire_idx=vcc_wire_idx,
                            site=bel_info.site,
                            site_variant=bel_info.site_variant,
                            synthetic_type=synthetic_type)

                        vcc_site_wires[bel_info.site] = vcc_site_wire_idx
                    src_wire_idx = vcc_site_wire_idx
                else:
                    continue

                # Create pip connecting constant network to site wire source.
                edge = PipInfo()
                edge.site = bel_info.site
                edge.site_variant = bel_info.site_variant
                edge_idx = len(tile_type.pip_data)
                tile_type.pip_data.append(edge)

                assert src_wire_idx is not None
                edge.src_index = src_wire_idx
                edge.dst_index = wire_idx
                edge.bel = len(tile_type.bel_data)

                # Create site PIP BEL for edge between constant network site
                # wire and site wire source.
                site_pip_bel = BelInfo()
                tile_type.bel_data.append(site_pip_bel)

                site_pip_bel.name = '{}_{}'.format(
                    bel_info.name, tile_type.wire_data[src_wire_idx].name)
                site_pip_bel.type = 'NA'

                site_pip_bel.ports.append(bel_info.name)
                site_pip_bel.types.append(PortType.PORT_IN.value)
                site_pip_bel.wires.append(src_wire_idx)

                site_pip_bel.ports.append(
                    tile_type.wire_data[src_wire_idx].name)
                site_pip_bel.types.append(PortType.PORT_OUT.value)
                site_pip_bel.wires.append(wire_idx)

                in_bel_port = BelPort()
                in_bel_port.bel_index = edge.bel
                in_bel_port.port = site_pip_bel.ports[0]
                tile_type.wire_data[src_wire_idx].bel_pins.append(in_bel_port)

                out_bel_port = BelPort()
                out_bel_port.bel_index = edge.bel
                out_bel_port.port = site_pip_bel.ports[1]
                tile_type.wire_data[wire_idx].bel_pins.append(out_bel_port)

                site_pip_bel.bel_bucket = 'UNPLACABLE_BELS'
                site_pip_bel.site = bel_info.site
                site_pip_bel.site_variant = bel_info.site_variant
                site_pip_bel.bel_category = BelCategory.ROUTING.value
                site_pip_bel.synthetic = synthetic_type.value

                # Update wire data pointing to new pip.
                tile_type.wire_data[src_wire_idx].pips_downhill.append(
                    edge_idx)
                tile_type.wire_data[wire_idx].pips_uphill.append(edge_idx)

        for wire_constant in tile_type_data.constants:
            if wire_constant.constant == 'gnd':
                src_wire_idx = gnd_wire_idx
            elif wire_constant.constant == 'vcc':
                src_wire_idx = vcc_wire_idx
            else:
                assert False, wire_constant.constant

            assert src_wire_idx is not None

            for wire_idx in wire_constant.wires:
                wire_name = device.strs[tile_type_data.wires[wire_idx]]

                assert tile_type.wire_data[wire_idx].name == wire_name, (
                    tile_type.wire_data[wire_idx].name, wire_name)

                # Create pip connecting constant network to wire source.
                edge = PipInfo()
                edge.site = -1
                edge_idx = len(tile_type.pip_data)
                tile_type.pip_data.append(edge)

                edge.src_index = src_wire_idx
                edge.dst_index = wire_idx
                edge.extra_data = -1

                # Update wire data pointing to new pip.
                tile_type.wire_data[src_wire_idx].pips_downhill.append(
                    edge_idx)
                tile_type.wire_data[wire_idx].pips_uphill.append(edge_idx)

    def build_input_site_port(self, tile_type_idx, port_name, site_wire_name,
                              tile_wire_idx, site, site_variant,
                              synthetic_type):
        tile_type = self.chip_info.tile_types[tile_type_idx]

        site_port_edge_idx = len(tile_type.pip_data)
        site_port_edge = PipInfo()
        tile_type.pip_data.append(site_port_edge)

        site_port_bel_idx = len(tile_type.bel_data)
        site_port_bel = BelInfo()
        tile_type.bel_data.append(site_port_bel)

        site_wire_idx = len(tile_type.wire_data)
        site_wire = TileWireInfo()
        tile_type.wire_data.append(site_wire)
        site_port_edge.site = site
        site_port_edge.site_variant = site_variant
        site_port_edge.bel = site_port_bel_idx

        site_port_edge.src_index = tile_wire_idx
        tile_type.wire_data[tile_wire_idx].pips_downhill.append(
            site_port_edge_idx)

        site_port_edge.dst_index = site_wire_idx
        site_wire.pips_uphill.append(site_port_edge_idx)

        site_port_bel.name = port_name
        site_port_bel.type = 'NA'
        site_port_bel.bel_bucket = 'UNPLACABLE_BELS'
        site_port_bel.ports.append(port_name)
        site_port_bel.types.append(PortType.PORT_OUT.value)
        site_port_bel.wires.append(site_wire_idx)
        site_port_bel.site = site
        site_port_bel.site_variant = site_variant
        site_port_bel.bel_category = BelCategory.SITE_PORT.value
        site_port_bel.synthetic = synthetic_type.value

        site_wire.name = site_wire_name
        site_wire_bel_port = BelPort()
        site_wire.bel_pins.append(site_wire_bel_port)
        site_wire.site = site
        site_wire.site_variant = site_variant

        site_wire_bel_port.bel_index = site_port_bel_idx
        site_wire_bel_port.port = port_name

        return site_wire_idx


def populate_macros(device, chip_info):
    prims = device.get_primitive_library()

    def get_cell(cell_type):
        # Gets the definition for a cell
        for lib in prims.libraries.values():
            if cell_type in lib.cells:
                return lib.cells[cell_type]
        return None

    if 'macros' in prims.libraries:
        macro_lib = prims.libraries['macros']
        for cell_name, cell in sorted(
                macro_lib.cells.items(), key=lambda x: x[0]):
            macro = Macro()
            macro.name = cell_name
            # Import instances
            for inst_name, inst in sorted(
                    cell.cell_instances.items(), key=lambda x: x[0]):
                macro_inst = MacroCellInst()
                macro_inst.name = inst_name
                macro_inst.type = inst.cell_name
                for key, value in sorted(
                        inst.property_map.items(), key=lambda x: x[0]):
                    param = MacroParameter()
                    param.key = key
                    param.value = value
                    macro_inst.parameters.append(param)
                macro.cell_insts.append(macro_inst)
            # Import nets
            for net_name, net in sorted(cell.nets.items(), key=lambda x: x[0]):
                macro_net = MacroNet()
                macro_net.name = net_name
                for port in net.ports:
                    macro_port = MacroPortInst()
                    macro_port.port = port.name
                    # Flatten buses
                    if port.idx is not None:
                        macro_port.port += '[{}]'.format(port.idx)
                    # Determine if this port is an instance port or top-level
                    if port.instance_name is not None:
                        macro_port.instance = port.instance_name
                        # Obtain direction from instance cell
                        cell_type = cell.cell_instances[
                            port.instance_name].cell_name
                        inst_cell = get_cell(cell_type)
                        assert inst_cell is not None, cell_type
                        macro_port.dir = inst_cell.ports[port.
                                                         name].direction.value
                    else:
                        # Instance is explicitly empty for top level ports
                        macro_port.instance = ('', )
                        # Obtain direction from macro ports
                        macro_port.dir = cell.ports[port.name].direction.value
                    macro_net.ports.append(macro_port)
                macro.nets.append(macro_net)
            chip_info.macros.append(macro)


def populate_macro_rules(device, chip_info):
    for rule in device.device_resource_capnp.exceptionMap:
        exp_data = MacroExpansion()
        exp_data.prim_name = device.strs[rule.primName]
        exp_data.macro_name = device.strs[rule.macroName]
        if rule.which() == 'parameters':
            for param in rule.parameters:
                param_match = MacroParameter()
                param_match.key = device.strs[param.key]
                param_match.value = device.strs[param.textValue]
                exp_data.param_matches.append(param_match)
        for mapping in rule.paramMapping:
            param_map = MacroParamMapRule()
            param_map.prim_param = device.strs[mapping.primParam]
            param_map.inst_name = device.strs[mapping.instName]
            param_map.inst_param = device.strs[mapping.instParam]
            if mapping.which() == 'copyValue':
                param_map.rule_type = MacroParamRuleType.COPY.value
            elif mapping.which() == 'bitSlice':
                param_map.rule_type = MacroParamRuleType.SLICE.value
                for bit in mapping.bitSlice:
                    param_map.slice_bits.append(bit)
            elif mapping.which() == 'tableLookup':
                param_map.rule_type = MacroParamRuleType.TABLE.value
                for entry in mapping.tableLookup:
                    table_entry = MacroParameter()
                    table_entry.key = device.strs[getattr(entry, 'from')]
                    table_entry.value = device.strs[entry.to]
                    param_map.map_table.append(table_entry)
            exp_data.param_rules.append(param_map)
        chip_info.macro_rules.append(exp_data)


def populate_chip_info(device, constids, device_config):
    assert len(constids.values) == 1

    bel_bucket_seeds = device_config.get('buckets', [])
    global_buffer_bels = device_config.get('global_buffer_bels', [])
    disabled_routethrus = device_config.get('disabled_routethroughs', [])
    disabled_cell_bel_map = device_config.get('disabled_cell_bel_map', [])
    global_buffer_cells = device_config.get('global_buffer_cells', [])

    cell_bel_mapper = CellBelMapper(device, constids, disabled_cell_bel_map)

    # Make the BEL buckets.
    for bucket in bel_bucket_seeds:
        bel_bucket = bucket['bucket']
        cells = bucket['cells']
        cell_bel_mapper.make_bel_bucket(bel_bucket, cells)

    cell_bel_mapper.handle_remaining()
    if DEBUG_BEL_BUCKETS:
        print_bel_buckets(cell_bel_mapper)

    chip_info = ChipInfo()
    chip_info.name = device.device_resource_capnp.name
    # FIXME: Pull version from scm version once integrated.
    chip_info.generator = 'python-fpga-interchange v0.0.2'
    # Version is updated in chip_info.py

    # Emit cells in const ID order to build cell map.
    for cell_name in cell_bel_mapper.get_cells():
        chip_info.cell_map.add_cell(
            cell_name, cell_bel_mapper.cell_to_bel_bucket(cell_name))

    for bel_name in global_buffer_bels:
        chip_info.cell_map.add_global_buffer_bel(bel_name)

    for lut_cell in device.device_resource_capnp.lutDefinitions.lutCells:
        out = LutCell()
        out.cell = lut_cell.cell

        for pin in lut_cell.inputPins:
            out.input_pins.append(pin)

        assert lut_cell.equation.which(
        ) == 'initParam', lut_cell.equation.which()

        out.parameter = lut_cell.equation.initParam
        assert out.parameter != '', lut_cell

        chip_info.cell_map.lut_cells.append(out)

    if device.parameter_definitions is None:
        device.init_parameter_definitions()

    for (cell_type,
         parameter_name), definition in device.parameter_definitions.items():
        cell_parameter = CellParameter()
        cell_parameter.cell_type = cell_type
        cell_parameter.parameter = parameter_name
        cell_parameter.format = definition.string_format.value
        cell_parameter.default_value = definition.default_value

        chip_info.cell_map.cell_parameters.append(cell_parameter)

    for bel_bucket in sorted(set(cell_bel_mapper.get_bel_buckets())):
        chip_info.bel_buckets.append(bel_bucket)

    populate_macros(device, chip_info)
    populate_macro_rules(device, chip_info)

    tile_wire_to_wire_in_tile_index = []
    num_tile_wires = []

    constraints = device.get_constraints()

    lut_elements = {}
    for lut_element in device.device_resource_capnp.lutDefinitions.lutElements:
        assert lut_element.site not in lut_elements
        lut_elements[lut_element.site] = LutElementsEmitter(lut_element.luts)

    for tile_type_index, tile_type in enumerate(
            device.device_resource_capnp.tileTypeList):
        flattened_tile_type = FlattenedTileType(
            device, tile_type_index, tile_type, cell_bel_mapper, constraints,
            lut_elements, disabled_routethrus)

        tile_type_info = flattened_tile_type.create_tile_type_info(
            cell_bel_mapper)
        chip_info.tile_types.append(tile_type_info)

        # Create map of tile wires to wire in tile id.
        per_tile_map = {}
        for idx, wire in enumerate(tile_type_info.wire_data):
            if wire.site != -1:
                # Only care about tile wires!
                break

            assert wire.name not in per_tile_map
            per_tile_map[wire.name] = idx

        tile_wire_to_wire_in_tile_index.append(per_tile_map)
        if len(per_tile_map) == 0:
            num_tile_wires.append(0)
        else:
            num_tile_wires.append(max(per_tile_map.values()) + 1)

    constants = ConstantNetworkGenerator(device, chip_info, cell_bel_mapper)

    # Emit cell bel pin map.
    for key, idx in sorted(
            cell_bel_mapper.cell_site_bel_index.items(),
            key=lambda item: item[1]):
        cell_type, tile_type, site_index, site_type, bel = key

        cell_bel_map = CellBelMap(cell_type, tile_type, site_index, bel)
        chip_info.cell_map.cell_bel_map.append(cell_bel_map)

        pin_key = (cell_type, site_type, bel)
        if pin_key in cell_bel_mapper.cell_to_bel_common_pins:
            for (cell_pin,
                 bel_pin) in cell_bel_mapper.cell_to_bel_common_pins[pin_key]:
                cell_bel_map.common_pins.append(CellBelPin(cell_pin, bel_pin))

        if pin_key in cell_bel_mapper.cell_to_bel_parameter_pins:
            for (param_key, param_value
                 ), pins in cell_bel_mapper.cell_to_bel_parameter_pins[
                     pin_key].items():
                parameter = ParameterPins()
                parameter.key = param_key
                parameter.value = param_value
                for (cell_pin, bel_pin) in pins:
                    parameter.pins.append(CellBelPin(cell_pin, bel_pin))

                cell_bel_map.parameter_pins.append(parameter)

        cell_bel_map = chip_info.cell_map.cell_bel_map[idx]
        if idx in cell_bel_mapper.cell_to_bel_constraints:
            cell_bel_map.constraints = cell_bel_mapper.cell_to_bel_constraints[
                idx]

    # Emit default cell pin connections
    for conn in device.get_constants().DEFAULT_CONNS:
        conn_data = DefaultCellConnections()
        conn_data.cell_type = conn.cell_type
        for pin in conn.pins:
            pin_data = DefaultCellConnection()
            pin_data.name = pin.name
            pin_data.value = pin.value.value
            conn_data.cell_pins.append(pin_data)
        chip_info.constants.default_conns.append(conn_data)

    tiles = {}
    tile_name_to_tile_index = {}

    for tile_index, tile in enumerate(device.device_resource_capnp.tileList):
        tile_info = TileInstInfo()

        tile_info.name = device.strs[tile.name]
        tile_info.type = tile.type
        tile_info.tile_wire_to_node = list(
            [-1 for _ in range(num_tile_wires[tile.type])])
        tile_info.tile_wire_to_type = list(
            [-1 for _ in range(num_tile_wires[tile.type])])

        tile_type = device.device_resource_capnp.tileTypeList[tile.type]

        for site_type_in_tile_type, site in zip(tile_type.siteTypes,
                                                tile.sites):
            site_name = device.strs[site.name]

            # Emit primary type
            site_info = SiteInstInfo()
            site_type = device.device_resource_capnp.siteTypeList[
                site_type_in_tile_type.primaryType]
            site_type_name = device.strs[site_type.name]
            site_info.name = '{}.{}'.format(site_name, site_type_name)
            site_info.site_name = site_name
            site_info.site_type = site_type_name

            tile_info.sites.append(len(chip_info.sites))
            chip_info.sites.append(site_info)

            for site_variant, (alt_site_type_index, _) in enumerate(
                    zip(site_type.altSiteTypes,
                        site_type_in_tile_type.altPinsToPrimaryPins)):
                alt_site_info = SiteInstInfo()
                alt_site_type = device.device_resource_capnp.siteTypeList[
                    alt_site_type_index]
                alt_site_type_name = device.strs[alt_site_type.name]
                alt_site_info.name = '{}.{}'.format(site_name,
                                                    alt_site_type_name)
                alt_site_info.site_name = site_name
                alt_site_info.site_type = alt_site_type_name

                tile_info.sites.append(len(chip_info.sites))
                chip_info.sites.append(alt_site_info)

        assert len(tile_info.sites) == len(
            chip_info.tile_types[tile.type].site_types), (
                tile_info.name, len(tile_info.sites),
                len(chip_info.tile_types[tile.type].site_types))

        # (x, y) = (col, row)
        tiles[(tile.col, tile.row)] = (tile_index, tile_info)

    # Compute dimensions of grid
    xs, ys = zip(*tiles.keys())
    width = max(xs) + 1
    height = max(ys) + 1

    chip_info.width = width
    chip_info.height = height

    # Add tile instances to chip_info in row major order (per arch.h).
    for y in range(height):
        for x in range(width):
            key = x, y

            _, tile_info = tiles[key]
            tile_name_to_tile_index[tile_info.name] = len(chip_info.tiles)
            chip_info.tiles.append(tile_info)

    # Output nodes
    for idx, node in enumerate(device.device_resource_capnp.nodes):
        # Skip nodes with only 1 wire!
        if len(node.wires) == 1:
            continue

        node_info = NodeInfo()
        node_index = len(chip_info.nodes)
        chip_info.nodes.append(node_info)

        # FIXME: Replace with actual node name?
        node_info.name = 'node_{}'.format(node_index)

        for wire_index in node.wires:
            wire = device.device_resource_capnp.wires[wire_index]
            tile_name = device.strs[wire.tile]
            wire_name = device.strs[wire.wire]

            tile_index = tile_name_to_tile_index[tile_name]
            tile_info = chip_info.tiles[tile_index]

            # Make reference from tile to node.
            wire_in_tile_id = tile_wire_to_wire_in_tile_index[tile_info.
                                                              type][wire_name]
            assert wire_in_tile_id < len(tile_info.tile_wire_to_node), (
                wire_in_tile_id, len(tile_info.tile_wire_to_node),
                tile_info.type, wire_name)
            assert tile_info.tile_wire_to_node[wire_in_tile_id] == -1
            tile_info.tile_wire_to_node[wire_in_tile_id] = node_index

            # Make reference from node to tile.
            tile_wire = TileWireRef()
            tile_wire.tile = tile_index
            tile_wire.index = wire_in_tile_id

            node_info.tile_wires.append(tile_wire)

    for wire in device.device_resource_capnp.wires:
        # Assign wire types
        tile_name = device.strs[wire.tile]
        wire_name = device.strs[wire.wire]
        tile_index = tile_name_to_tile_index[tile_name]
        tile_info = chip_info.tiles[tile_index]
        wire_in_tile_id = tile_wire_to_wire_in_tile_index[tile_info.
                                                          type][wire_name]
        tile_info.tile_wire_to_type[wire_in_tile_id] = wire.type

    constants.populate_constant_network()

    for package in device.device_resource_capnp.packages:
        package_data = Package()
        package_data.package = device.strs[package.name]
        chip_info.packages.append(package_data)

        for package_pin in package.packagePins:
            if package_pin.site.which() == 'noSite':
                continue
            if package_pin.site.which() == 'noBel':
                continue

            package_pin_data = PackagePin()
            package_pin_data.package_pin = device.strs[package_pin.packagePin]
            package_pin_data.site = device.strs[package_pin.site.site]
            package_pin_data.bel = device.strs[package_pin.bel.bel]

            package_data.package_pins.append(package_pin_data)

    for wire_type in device.device_resource_capnp.wireTypes:
        wire_type_data = WireType()
        wire_type_data.name = device.strs[wire_type.name]
        wire_type_data.category = convert_wire_category(
            wire_type.category).value
        chip_info.wire_types.append(wire_type_data)

    for global_cell in global_buffer_cells:
        global_cell_data = GlobalCell()
        global_cell_data.cell_type = global_cell['cell']
        for pin in global_cell.get('pins', []):
            pin_data = GlobalCellPin()
            pin_data.name = pin['name']
            pin_data.max_hops = pin.get('max_hops', -1)
            pin_data.guide_placement = 1 if pin.get('guide_placement',
                                                    False) else 0
            pin_data.force_routing = 1 if pin.get('force_dedicated_routing',
                                                  False) else 0
            global_cell_data.pins.append(pin_data)
        chip_info.global_cells.append(global_cell_data)

    return chip_info
