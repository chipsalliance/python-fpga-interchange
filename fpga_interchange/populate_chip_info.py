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
from fpga_interchange.chip_info import ChipInfo, BelInfo, TileTypeInfo, \
        TileWireInfo, BelPort, PipInfo, TileInstInfo, SiteInstInfo, NodeInfo, \
        TileWireRef

from fpga_interchange.nextpnr import PortType
from enum import Enum
from collections import namedtuple


class FlattenedWireType(Enum):
    TILE_WIRE = 0
    SITE_WIRE = 1


class FlattenedPipType(Enum):
    TILE_PIP = 0
    SITE_PIP = 1
    SITE_PIN = 2


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


class FlattenedTileType():
    def __init__(self, device, tile_type_index, tile_type):
        self.tile_type_name = device.strs[tile_type.name]
        self.tile_type = tile_type

        self.sites = []
        self.bels = []
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
                               site_variant)

            for site_variant, (alt_site_type_index, _) in enumerate(
                    zip(primary_site_type.altSiteTypes,
                        site_type_in_tile_type.altPinsToPrimaryPins)):
                self.add_site_type(device, site_type_in_tile_type,
                                   site_in_type_index, alt_site_type_index,
                                   site_variant, primary_site_type)

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

        self.sites.append(
            FlattenedSite(
                site_in_type_index=site_in_type_index,
                site_type_index=site_type_index,
                site_type=site_type,
                site_type_name=device.strs[site_type.name],
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
                bel_category = 0
            elif bel.category == 'routing':
                bel_category = 1
            else:
                assert bel.category == 'sitePort', bel.category
                bel_category = 2

            flat_bel = FlattenedBel(
                name=device.strs[bel.name],
                type=device.strs[bel.type],
                site_index=site_index,
                bel_index=bel_idx,
                bel_category=bel_category)
            bel_index = len(self.bels)
            bel_to_bel_index[bel_idx] = bel_index
            self.bels.append(flat_bel)

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

    def create_tile_type_info(self, cell_bel_mapper):
        tile_type = TileTypeInfo()
        tile_type.name = self.tile_type_name
        tile_type.number_sites = len(self.sites)

        for bel in self.bels:
            bel_info = BelInfo()
            bel_info.name = bel.name
            bel_info.type = bel.type

            for port in bel.ports:
                bel_info.ports.append(port.port)
                bel_info.types.append(port.type.value)
                bel_info.wires.append(port.wire)

            bel_info.site = bel.site_index
            bel_info.site_variant = self.sites[bel.site_index].site_variant
            bel_info.bel_category = bel.bel_category

            site_type = self.sites[bel.site_index].site_type_name

            bel_key = (site_type, bel.name)
            bel_info.bel_bucket = cell_bel_mapper.bel_to_bel_bucket(*bel_key)

            bel_info.valid_cells = [0 for _ in cell_bel_mapper.get_cells()]
            # Pad to align with 32-bit
            while len(bel_info.valid_cells) % 4 != 0:
                bel_info.valid_cells.append(0)

            for idx, cell in enumerate(cell_bel_mapper.get_cells()):
                if bel in cell_bel_mapper.bels_for_cell(cell):
                    bel_info.valid_cells[idx] = 1

            tile_type.bel_data.append(bel_info)

        for wire in self.wires:
            wire_info = TileWireInfo()
            wire_info.name = wire.name
            wire_info.pips_uphill = wire.pips_uphill
            wire_info.pips_downhill = wire.pips_downhill

            for (bel_index, port) in wire.bel_pins:
                bel_port = BelPort()
                bel_port.bel_index = bel_index
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
                    pip_info.bel = site.bel_to_bel_index[bel_idx]
                    pip_info.extra_data = pin_idx
                else:
                    assert pip.type == FlattenedPipType.SITE_PIN
                    site_pin = site_type.pins[pip.pip_index]
                    bel_idx, pin_idx = site.bel_pin_index_to_bel_index[
                        site_pin.belpin]
                    pip_info.bel = site.bel_to_bel_index[bel_idx]
                    pip_info.extra_data = pin_idx
            else:
                assert pip.type == FlattenedPipType.TILE_PIP
                pip_info.site = -1
                pip_info.site_variant = -1

            tile_type.pip_data.append(pip_info)

        return tile_type


class CellBelMapper():
    def __init__(self, device, constids):
        # Emit cell names so that they are compact list.
        self.cells_in_order = []
        self.cell_names = {}
        self.bel_buckets = set()
        self.cell_to_bel_buckets = {}
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
            cell_name = device.strs[cell_bel_map.cell]
            assert cell_name in self.cell_names

            bels = set()

            for pins in cell_bel_map.commonPins:
                for site_types_and_bels in pins.siteTypes:
                    site_type = device.strs[site_types_and_bels.siteType]
                    for bel_str_id in site_types_and_bels.bels:
                        bel = device.strs[bel_str_id]
                        bels.add((site_type, bel))

            for pins in cell_bel_map.parameterPins:
                for site_types_and_bels in pins.parametersSiteTypes:
                    bel = device.strs[site_types_and_bels.bel]
                    site_type = device.strs[site_types_and_bels.siteType]
                    bels.add((site_type, bel))

            self.cell_to_bel_map[cell_name] = bels

        self.bels = set()
        for site_type in device.device_resource_capnp.siteTypeList:
            for bel in site_type.bels:
                self.bels.add((device.strs[site_type.name],
                               device.strs[bel.name]))

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

# TODO: Read BEL_BUCKET_SEEDS from input (e.g. device or input file).
BEL_BUCKET_SEEDS = (
    ('FLIP_FLOPS', ('FDRE', )),
    ('LUTS', ('LUT1', )),
    ('BRAMS', ('RAMB18E1', 'RAMB36E1', 'FIFO18E1', 'FIFO36E1')),
    ('BUFG', ('BUFG', 'BUFGCTRL')),
    ('BUFH', ('BUFH', 'BUFHCE')),
    ('BUFMR', ('BUFMR', )),
    ('BUFR', ('BUFR', )),
    ('IBUFs', ('IBUF', 'IBUFDS_IBUFDISABLE_INT')),
    ('OBUFs', ('OBUF', 'OBUFTDS')),
    ('MMCM', ('MMCME2_ADV', )),
    ('PLL', ('PLLE2_BASE', )),
    ('PULLs', ('PULLDOWN', )),
    ('CARRY', ('MUXCY', 'XORCY', 'CARRY4')),
)


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


def populate_chip_info(device, constids):
    assert len(constids.values) == 0

    cell_bel_mapper = CellBelMapper(device, constids)

    # Make the BEL buckets.
    for bel_bucket, cells in BEL_BUCKET_SEEDS:
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

    for tile_type_index, tile_type in enumerate(
            device.device_resource_capnp.tileTypeList):
        flattened_tile_type = FlattenedTileType(device, tile_type_index,
                                                tile_type)

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

    #import pdb; pdb.set_trace()

    return chip_info
