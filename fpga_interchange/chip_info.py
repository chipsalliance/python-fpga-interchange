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


class BelInfo():
    str_id_fields = ['ports']
    int_fields = ['types', 'wires']

    def __init__(self):
        # BEL name, str
        self.name = ''
        # BEL type, str
        self.type = ''
        # BEL bucket, str
        self.bel_bucket = ''

        # BEL port names, str
        self.ports = []
        # BEL port names, PortType
        self.types = []
        # Site wire index, int
        self.wires = []

        # Index into tile site array
        self.site = 0

        # -1 if site is a primary type, otherwise index into altSiteTypes.
        self.site_variant = 0

        # What type of BEL is this?
        self.bel_category = 0

        # Bool array (length number of cells).
        self.valid_cells = []

    def field_label(self, label_prefix, field):
        prefix = '{}.site{}.{}.{}'.format(label_prefix, self.site, self.name,
                                          field)
        return prefix

    def append_children_bba(self, bba, label_prefix):
        assert len(self.ports) == len(self.types)
        assert len(self.ports) == len(self.wires)

        for field in self.str_id_fields:
            bba.label(self.field_label(label_prefix, field), 'str_id')
            for value in getattr(self, field):
                bba.str_id(value)

        for field in self.int_fields:
            bba.label(self.field_label(label_prefix, field), 'int32_t')
            for value in getattr(self, field):
                bba.u32(value)

        bba.label(self.field_label(label_prefix, 'valid_cells'), 'int8_t')
        for value in self.valid_cells:
            bba.u8(value)

    def append_bba(self, bba, label_prefix):
        bba.str_id(self.name)
        bba.str_id(self.type)
        bba.str_id(self.bel_bucket)
        bba.u32(len(self.ports))

        for field in self.str_id_fields:
            bba.ref(self.field_label(label_prefix, field))

        for field in self.int_fields:
            bba.ref(self.field_label(label_prefix, field))

        bba.u16(self.site)
        bba.u16(self.site_variant)
        bba.u16(self.bel_category)
        bba.u16(0)

        bba.ref(self.field_label(label_prefix, 'valid_cells'))


class BelPort():
    def __init__(self):
        # Index into tile_type.bel_data
        self.bel_index = 0
        self.port = ''

    def append_children_bba(self, bba, label_prefix):
        pass

    def append_bba(self, bba, label_prefix):
        bba.u32(self.bel_index)
        bba.str_id(self.port)


class TileWireInfo():
    def __init__(self):
        # Wire name, str
        self.name = ''

        # Index into tile_type.pip_data
        self.pips_uphill = []
        self.pips_downhill = []

        # BelPorts
        self.bel_pins = []

        # Index into tile site array
        self.site = 0

        # -1 if site is a primary type, otherwise index into altSiteTypes.
        self.site_variant = 0

    def field_label(self, label_prefix, field):
        if self.site != -1:
            prefix = '{}.site{}.{}.{}'.format(label_prefix, self.site,
                                              self.name, field)
        else:
            prefix = '{}.{}.{}'.format(label_prefix, self.name, field)

        return prefix

    def append_children_bba(self, bba, label_prefix):
        for int_field in ['pips_uphill', 'pips_downhill']:
            prefix = self.field_label(label_prefix, int_field)

            bba.label(prefix, 'int32_t')
            for value in getattr(self, int_field):
                bba.u32(value)

        prefix = self.field_label(label_prefix, 'bel_pins')
        for value in self.bel_pins:
            value.append_children_bba(bba, prefix)

        bba.label(prefix, 'BelPortPOD')
        for value in self.bel_pins:
            value.append_bba(bba, prefix)

    def append_bba(self, bba, label_prefix):
        bba.str_id(self.name)

        for field in ['pips_uphill', 'pips_downhill', 'bel_pins']:
            bba.u32(len(getattr(self, field)))
            bba.ref(self.field_label(label_prefix, field))

        bba.u16(self.site)
        bba.u16(self.site_variant)


class PipInfo():
    def __init__(self):
        # Index into tile_type.wire_data
        self.src_index = 0

        # Index into tile_type.wire_data
        self.dst_index = 0

        # Index into tile site array
        self.site = 0

        # -1 if site is a primary type, otherwise index into altSiteTypes.
        self.site_variant = 0

        # Index into tile_type.bel_data.
        self.bel = 0

        self.extra_data = 0

    def append_children_bba(self, bba, label_prefix):
        pass

    def append_bba(self, bba, label_prefix):
        bba.u32(self.src_index)
        bba.u32(self.dst_index)
        bba.u16(self.site)
        bba.u16(self.site_variant)
        bba.u16(self.bel)
        bba.u16(self.extra_data)


class TileTypeInfo():
    children_fields = ['bel_data', 'wire_data', 'pip_data']
    children_types = ['BelInfoPOD', 'TileWireInfoPOD', 'PipInfoPOD']

    def __init__(self):
        # Tile type name
        self.name = ''

        # Number of sites
        self.number_sites = 0

        # Array of BelInfo
        self.bel_data = []

        # Array of TileWireInfo
        self.wire_data = []

        # Array of PipInfo
        self.pip_data = []

    def field_label(self, label_prefix, field):
        prefix = '{}.{}.{}'.format(label_prefix, self.name, field)
        return prefix

    def append_children_bba(self, bba, label_prefix):
        label = label_prefix

        for field, field_type in zip(self.children_fields,
                                     self.children_types):
            prefix = self.field_label(label, field)
            for value in getattr(self, field):
                value.append_children_bba(bba, prefix)

            bba.label(prefix, field_type)
            for value in getattr(self, field):
                value.append_bba(bba, prefix)

    def append_bba(self, bba, label_prefix):
        bba.str_id(self.name)
        bba.u32(self.number_sites)

        for field in self.children_fields:
            bba.u32(len(getattr(self, field)))
            bba.ref(self.field_label(label_prefix, field))


class SiteInstInfo():
    def __init__(self):
        # Site instance name
        # <site>.<site type>
        self.name = ''

        # Site type name
        self.site_type = ''

    def append_children_bba(self, bba, label_prefix):
        pass

    def append_bba(self, bba, label_prefix):
        bba.str(self.name)
        bba.str_id(self.site_type)


class TileInstInfo():
    def __init__(self):
        # Tile instance name
        self.name = ''

        # Index into tile_types
        self.type = 0

        # Index into root.sites
        self.sites = []

        # Index into root.nodes
        self.tile_wire_to_node = []

    def sites_label(self, label_prefix):
        return '{}.{}.sites'.format(label_prefix, self.name)

    def tile_wire_to_node_label(self, label_prefix):
        return '{}.{}.tile_wire_to_node'.format(label_prefix, self.name)

    def append_children_bba(self, bba, label_prefix):
        bba.label(self.sites_label(label_prefix), 'int32_t')
        for site in self.sites:
            bba.u32(site)

        bba.label(self.tile_wire_to_node_label(label_prefix), 'int32_t')
        for node_index in self.tile_wire_to_node:
            bba.u32(node_index)

    def append_bba(self, bba, label_prefix):
        bba.str(self.name)
        bba.u32(self.type)
        bba.ref(self.sites_label(label_prefix))
        bba.u32(len(self.tile_wire_to_node))
        bba.ref(self.tile_wire_to_node_label(label_prefix))


class TileWireRef():
    def __init__(self):
        self.tile = 0
        self.index = 0

    def append_bba(self, bba, label_prefix):
        bba.u32(self.tile)
        bba.u32(self.index)


class NodeInfo():
    def __init__(self):
        self.name = ''
        self.tile_wires = []

    def tile_wires_label(self, label_prefix):
        return '{}.{}.tile_wires'.format(label_prefix, self.name)

    def append_children_bba(self, bba, label_prefix):
        label = self.tile_wires_label(label_prefix)
        bba.label(label, 'TileWireRefPOD')
        for tile_wire in self.tile_wires:
            tile_wire.append_bba(bba, label)

    def append_bba(self, bba, label_prefix):
        bba.u32(len(self.tile_wires))
        bba.ref(self.tile_wires_label(label_prefix))


class CellMap():
    fields = ['cell_names', 'cell_bel_buckets']

    def __init__(self):
        self.cell_names = []
        self.cell_bel_buckets = []

    def add_cell(self, cell_name, cell_bel_bucket):
        self.cell_names.append(cell_name)
        self.cell_bel_buckets.append(cell_bel_bucket)

    def field_label(self, label_prefix, field):
        prefix = '{}.{}'.format(label_prefix, field)
        return prefix

    def append_children_bba(self, bba, label_prefix):
        assert len(self.cell_names) == len(self.cell_bel_buckets)

        for field in self.fields:
            bba.label(self.field_label(label_prefix, field), 'uint32_t')
            for s in getattr(self, field):
                bba.str_id(s)

    def append_bba(self, bba, label_prefix):
        assert len(self.cell_names) == len(self.cell_bel_buckets)
        bba.u32(len(self.cell_names))

        for field in self.fields:
            bba.ref(self.field_label(label_prefix, field))


class ChipInfo():
    def __init__(self):
        self.name = ''
        self.generator = ''

        self.version = 0
        self.width = 0
        self.height = 0

        self.tile_types = []
        self.sites = []
        self.tiles = []
        self.nodes = []

        # str, constids
        self.bel_buckets = []

        self.cell_map = CellMap()

    def append_bba(self, bba, label_prefix):
        label = label_prefix

        children_fields = ['tile_types', 'sites', 'tiles', 'nodes']
        children_types = [
            'TileTypeInfoPOD', 'SiteInstInfoPOD', 'TileInstInfoPOD',
            'NodeInfoPOD'
        ]
        for field, field_type in zip(children_fields, children_types):
            prefix = '{}.{}'.format(label, field)
            for value in getattr(self, field):
                value.append_children_bba(bba, prefix)

            bba.label(prefix, field_type)
            for value in getattr(self, field):
                value.append_bba(bba, prefix)

        bba.label('{}.bel_buckets'.format(label), 'uint32_t')
        for s in self.bel_buckets:
            bba.str_id(s)

        cell_map_prefix = '{}.cell_map'.format(label)
        self.cell_map.append_children_bba(bba, cell_map_prefix)

        bba.label(cell_map_prefix, 'CellMapPOD')
        self.cell_map.append_bba(bba, cell_map_prefix)

        bba.label(label, 'ChipInfoPOD')
        bba.str(self.name)
        bba.str(self.generator)
        bba.u32(self.version)
        bba.u32(self.width)
        bba.u32(self.height)

        for field in children_fields:
            bba.u32(len(getattr(self, field)))
            bba.ref('{}.{}'.format(label, field))

        bba.u32(len(self.bel_buckets))
        bba.ref('{}.bel_buckets'.format(label))

        bba.ref('{}.cell_map'.format(label))
