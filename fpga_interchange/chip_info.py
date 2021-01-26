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
    int_fields = ['ports', 'types', 'wires']

    def __init__(self):
        # BEL name, str
        self.name = ''
        # BEL type, str
        self.type = ''

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

        # Is this a routing BEL?
        self.is_routing = False

    def field_label(self, label_prefix, field):
        prefix = '{}.{}.{}'.format(label_prefix, self.name, field)
        return prefix

    def append_children_bba(self, bba, label_prefix):
        assert len(self.ports) == len(self.types)
        assert len(self.ports) == len(self.wires)

        for field in self.int_fields:
            bba.label(self.field_label(label_prefix, field), 'int32_t')
            for value in getattr(self, field):
                bba.u32(value)

    def append_bba(self, bba, label_prefix):
        bba.str_id(self.name)
        bba.str_id(self.type)
        bba.u32(len(self.ports))
        for field in self.int_fields:
            bba.ref(self.field_label(label_prefix, field))

        bba.u16(self.site)
        bba.u16(self.site_variant)
        bba.u16(self.is_routing)
        bba.u16(0)


class BelPort():
    def __init__(self):
        # Index into tile_type.bel_data
        self.bel_index = 0
        # Index into tile_type.bel_data[bel_index].ports/types/wires
        self.port = 0

    def append_children_bba(self, bba, label_prefix):
        pass

    def append_bba(self, bba, label_prefix):
        bba.u32(self.bel_index)
        bba.u32(self.port)


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
            bba.u32(len(self.pips_uphill))
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
        self.u32(self.src_index)
        self.u32(self.dst_index)
        self.u16(self.site)
        self.u16(self.site_variant)
        self.u16(self.bel)
        self.u16(self.extra_data)


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
        self.pip_info = []

    def field_label(self, label_prefix, field):
        prefix = '{}.{}.{}'.format(label_prefix, self.name, field)
        return prefix

    def append_children_bba(self, bba, label_prefix):
        label = label_prefix

        for field, field_type in zip(self.children_fields, self.children_types):
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
            self.u32(len(getattr(self, field)))
            self.ref(self.field_label(label_prefix, field))

class SiteInstInfo():
    def __init__(self):
        # Site instance name
        # <site>.<site type>
        self.name = ''

    def append_children_bba(self, bba, label_prefix):
        pass

    def append_bba(self, bba, label_prefix):
        bba.str(self.name)
        bba.std_id(self.site_type)

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

    def append_bba(self, bba, label_prefix):
        label = label_prefix


        children_fields = ['tile_types', 'sites', 'tiles', 'nodes']
        children_types = ['TileTypeInfoPOD', 'SiteInstInfoPOD', 'TileInstInfoPOD', 'NodeInfoPOD']
        for field, field_type in zip(children_fields, children_types):
            prefix = '{}.{}'.format(label, field)
            for value in getattr(self, field):
                value.append_children_bba(bba, prefix)

            bba.label(prefix, field_type)
            for value in getattr(self, field):
                value.append_bba(bba, prefix)

        bba.label(label, 'ChipInfoPOD')
        bba.str(self.name)
        bba.str(self.generator)
        bba.u32(self.version)
        bba.u32(self.width)
        bba.u32(self.height)

        for field in children_fields:
            bba.u32(len(getattr(self, field)))
            bba.ref('{}.{}'.format(label, field))
