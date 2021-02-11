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
        CellConstraint, ConstraintType, Package, PackagePin
from fpga_interchange.constraints.model import Tag, Placement, \
        ImpliesConstraint, RequiresConstraint
from fpga_interchange.constraint_generator import ConstraintPrototype
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
    def __init__(self, name, type, site_index, bel_index, bel_category):
        self.name = name
        self.type = type
        self.site_index = site_index
        self.bel_index = bel_index
        self.bel_category = bel_category
        self.ports = []

        self.valid_cells = set()

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
        namedtuple('FlattenedPip',
                   'type src_index dst_index site_index pip_index')):
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


class FlattenedTileType():
    def __init__(self, device, tile_type_index, tile_type, cell_bel_mapper,
                 constraints):
        self.tile_type_name = device.strs[tile_type.name]
        self.tile_type = tile_type

        self.tile_constraints = ConstraintPrototype()

        self.sites = []
        self.bels = []
        self.bel_index_remap = {}
        self.wires = []

        self.pips = []

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

        # Add pips
        for idx, pip in enumerate(tile_type.pips):
            # TODO: Handle pseudoCells
            self.add_tile_pip(idx, pip.wire0, pip.wire1)

            if not pip.directional:
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
                               site_variant, cell_bel_mapper)

            for site_variant, (alt_site_type_index, _) in enumerate(
                    zip(primary_site_type.altSiteTypes,
                        site_type_in_tile_type.altPinsToPrimaryPins)):
                self.add_site_type(device, site_type_in_tile_type,
                                   site_in_type_index, alt_site_type_index,
                                   site_variant, cell_bel_mapper,
                                   primary_site_type)
        self.remap_bel_indicies()
        self.generate_constraints(constraints)

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

    def add_tile_pip(self, tile_pip_index, src_wire, dst_wire):
        assert self.wires[src_wire].type == FlattenedWireType.TILE_WIRE
        assert self.wires[dst_wire].type == FlattenedWireType.TILE_WIRE

        flat_pip = FlattenedPip(
            type=FlattenedPipType.TILE_PIP,
            src_index=src_wire,
            dst_index=dst_wire,
            site_index=None,
            pip_index=tile_pip_index)

        self.add_pip_common(flat_pip)

    def add_site_type(self,
                      device,
                      site_type_in_tile_type,
                      site_in_type_index,
                      site_type_index,
                      site_variant,
                      cell_bel_mapper,
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
                bel_category=bel_category)
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
            pip_index=site_pip_index)

        self.add_pip_common(flat_pip)

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
            pip_index=site_pin_index)

        self.add_pip_common(flat_pip)

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
        tile_type.number_sites = len(self.sites)

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

        return tile_type


class CellBelMapper():
    def __init__(self, device, constids):
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

        return self.cell_site_bel_index.get(key, -1)

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


def populate_chip_info(device, constids, bel_bucket_seeds):
    assert len(constids.values) == 0

    cell_bel_mapper = CellBelMapper(device, constids)

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
    chip_info.generator = 'python-fpga-interchange v0.x'
    chip_info.version = 1

    # Emit cells in const ID order to build cell map.
    for cell_name in cell_bel_mapper.get_cells():
        chip_info.cell_map.add_cell(
            cell_name, cell_bel_mapper.cell_to_bel_bucket(cell_name))

    for bel_bucket in sorted(set(cell_bel_mapper.get_bel_buckets())):
        chip_info.bel_buckets.append(bel_bucket)

    tile_wire_to_wire_in_tile_index = []
    num_tile_wires = []

    constraints = device.get_constraints()

    for tile_type_index, tile_type in enumerate(
            device.device_resource_capnp.tileTypeList):
        flattened_tile_type = FlattenedTileType(
            device, tile_type_index, tile_type, cell_bel_mapper, constraints)

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
        num_tile_wires.append(max(per_tile_map.values()) + 1)

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
                    cell_bel_map.parameter_pins.append(
                        CellBelPin(cell_pin, bel_pin))

                cell_bel_map.parameter_pins.append(parameter)

        cell_bel_map = chip_info.cell_map.cell_bel_map[idx]
        if idx in cell_bel_mapper.cell_to_bel_constraints:
            cell_bel_map.constraints = cell_bel_mapper.cell_to_bel_constraints[
                idx]

    tiles = {}
    tile_name_to_tile_index = {}

    for tile_index, tile in enumerate(device.device_resource_capnp.tileList):
        tile_info = TileInstInfo()

        tile_info.name = device.strs[tile.name]
        tile_info.type = tile.type
        tile_info.tile_wire_to_node = list(
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

        assert len(
            tile_info.sites) == chip_info.tile_types[tile.type].number_sites, (
                tile_info.name, len(tile_info.sites),
                chip_info.tile_types[tile.type].number_sites)

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

        # FIXME: Replace with actual node name?
        node_info.name = 'node{}'.format(idx)

        node_index = len(chip_info.nodes)
        chip_info.nodes.append(node_info)

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

    return chip_info
