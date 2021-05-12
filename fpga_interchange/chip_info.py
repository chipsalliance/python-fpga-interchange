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

# Note: Increment by 1 ChipInfo.version number each time schema changes to
# allow nextpnr binary to detect changes to schema.


class ConstraintType(Enum):
    TAG_IMPLIES = 0
    TAG_REQUIRES = 1


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

        # Is this a synthetic BEL?
        self.synthetic = 0

        # -1 if this is not a LUT type BEL, index into tile_type.lut_elements.
        self.lut_element = -1

        # Index into CellMapPOD::cell_bel_pin_map
        self.pin_map = []

        # Index into ports/types/wires if this BEL has inverting site pips.
        self.non_inverting_pin = -1
        self.inverting_pin = -1

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

        bba.label(self.field_label(label_prefix, 'pin_map'), 'int32_t')
        for value in self.pin_map:
            bba.u32(value)

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
        bba.u8(self.synthetic)
        bba.u8(self.lut_element)

        bba.ref(self.field_label(label_prefix, 'pin_map'))

        bba.u8(self.non_inverting_pin)
        bba.u8(self.inverting_pin)

        # Pad to nearest 32-bit alignment
        bba.u16(0)


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
            bba.ref(self.field_label(label_prefix, field))
            bba.u32(len(getattr(self, field)))

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

        self.pseudo_cell_wires = []

    def field_label(self, label_prefix, field):
        return '{}.{}.{}.{}.{}'.format(label_prefix, self.src_index,
                                       self.dst_index, self.extra_data, field)

    def append_children_bba(self, bba, label_prefix):
        bba.label(
            self.field_label(label_prefix, 'pseudo_cell_wires'), 'int32_t')
        for wire in self.pseudo_cell_wires:
            bba.u32(wire)

    def append_bba(self, bba, label_prefix):
        assert self.src_index != -1
        assert self.dst_index != -1

        bba.u32(self.src_index)
        bba.u32(self.dst_index)
        bba.u16(self.site)
        bba.u16(self.site_variant)
        bba.u16(self.bel)
        bba.u16(self.extra_data)
        bba.ref(self.field_label(label_prefix, 'pseudo_cell_wires'))
        bba.u32(len(self.pseudo_cell_wires))


class ConstraintTag():
    def __init__(self):
        self.tag_prefix = ''
        self.default_state = ''
        self.states = []

    def field_label(self, label_prefix, field):
        prefix = '{}.{}.{}'.format(label_prefix, self.tag_prefix, field)
        return prefix

    def append_children_bba(self, bba, label_prefix):
        bba.label(self.field_label(label_prefix, 'states'), 'constids')
        for s in self.states:
            bba.str_id(s)

    def append_bba(self, bba, label_prefix):
        bba.str_id(self.tag_prefix)
        bba.str_id(self.default_state)
        bba.ref(self.field_label(label_prefix, 'states'))
        bba.u32(len(self.states))


class LutBel():
    def __init__(self):
        self.name = ''
        self.pins = []
        self.low_bit = 0
        self.high_bit = 0
        self.out_pin = ''

    def field_label(self, label_prefix, field):
        prefix = '{}.{}.{}'.format(label_prefix, self.name, field)
        return prefix

    def append_children_bba(self, bba, label_prefix):
        bba.label(self.field_label(label_prefix, 'pins'), 'constids')
        for pin in self.pins:
            bba.str_id(pin)

    def append_bba(self, bba, label_prefix):
        bba.str_id(self.name)
        bba.ref(self.field_label(label_prefix, 'pins'))
        bba.u32(len(self.pins))
        bba.u32(self.low_bit)
        bba.u32(self.high_bit)
        bba.str_id(self.out_pin)


class LutElement():
    def __init__(self, lut_element_idx):
        self.lut_element_idx = lut_element_idx
        self.width = 0
        self.lut_bels = []

    def field_label(self, label_prefix, field):
        prefix = '{}.{}.{}'.format(label_prefix, self.lut_element_idx, field)
        return prefix

    def append_children_bba(self, bba, label_prefix):
        label = self.field_label(label_prefix, 'lut_bels')
        for lut_bel in self.lut_bels:
            lut_bel.append_children_bba(bba, label)

        bba.label(label, 'LutBelPOD')
        for lut_bel in self.lut_bels:
            lut_bel.append_bba(bba, label)

    def append_bba(self, bba, label_prefix):
        bba.u32(self.width)
        bba.ref(self.field_label(label_prefix, 'lut_bels'))
        bba.u32(len(self.lut_bels))


class TileTypeInfo():
    children_fields = [
        'bel_data', 'wire_data', 'pip_data', 'tags', 'lut_elements'
    ]
    children_types = [
        'BelInfoPOD', 'TileWireInfoPOD', 'PipInfoPOD', 'ConstraintTagPOD',
        'LutElementPOD'
    ]

    def __init__(self):
        # Tile type name
        self.name = ''

        # Array of BelInfo
        self.bel_data = []

        # Array of TileWireInfo
        self.wire_data = []

        # Array of PipInfo
        self.pip_data = []

        # Array of ConstraintTag
        self.tags = []

        # Array of LutElement
        self.lut_elements = []

        # Array of str
        self.site_types = []

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

        bba.label(self.field_label(label, 'site_types'), 'constid')
        for site_type in self.site_types:
            bba.str_id(site_type)

    def append_bba(self, bba, label_prefix):
        bba.str_id(self.name)

        for field in self.children_fields:
            bba.ref(self.field_label(label_prefix, field))
            bba.u32(len(getattr(self, field)))

        bba.ref(self.field_label(label_prefix, 'site_types'))
        bba.u32(len(self.site_types))


class SiteInstInfo():
    def __init__(self):
        # Site instance name
        # <site>.<site type>
        self.name = ''

        self.site_name = ''

        # Site type name
        self.site_type = ''

    def append_children_bba(self, bba, label_prefix):
        pass

    def append_bba(self, bba, label_prefix):
        bba.str(self.name)
        bba.str(self.site_name)
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

        # Index into root.wire_types
        self.tile_wire_to_type = []

    def sites_label(self, label_prefix):
        return '{}.{}.sites'.format(label_prefix, self.name)

    def tile_wire_to_node_label(self, label_prefix):
        return '{}.{}.tile_wire_to_node'.format(label_prefix, self.name)

    def tile_wire_to_type_label(self, label_prefix):
        return '{}.{}.tile_wire_to_type'.format(label_prefix, self.name)

    def append_children_bba(self, bba, label_prefix):
        bba.label(self.sites_label(label_prefix), 'int32_t')
        for site in self.sites:
            bba.u32(site)

        bba.label(self.tile_wire_to_node_label(label_prefix), 'int32_t')
        for node_index in self.tile_wire_to_node:
            bba.u32(node_index)
        bba.label(self.tile_wire_to_type_label(label_prefix), 'int16_t')
        for type_index in self.tile_wire_to_type:
            bba.u16(type_index)
        if len(self.tile_wire_to_type) % 2 == 1:
            # Pad to nearest 32-bit alignment
            bba.u16(0)

    def append_bba(self, bba, label_prefix):
        bba.str(self.name)
        bba.u32(self.type)
        bba.ref(self.sites_label(label_prefix))
        bba.u32(len(self.sites))
        bba.ref(self.tile_wire_to_node_label(label_prefix))
        bba.u32(len(self.tile_wire_to_node))
        bba.ref(self.tile_wire_to_type_label(label_prefix))
        bba.u32(len(self.tile_wire_to_type))


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
        bba.ref(self.tile_wires_label(label_prefix))
        bba.u32(len(self.tile_wires))


class CellBelPin():
    def __init__(self, cell_pin, bel_pin):
        self.cell_pin = cell_pin
        self.bel_pin = bel_pin

    def append_children_bba(self, bba, label_prefix):
        pass

    def append_bba(self, bba, label_prefix):
        bba.str_id(self.cell_pin)
        bba.str_id(self.bel_pin)


class ParameterPins():
    def __init__(self):
        self.key = ''
        self.value = ''
        self.pins = []

    def field_label(self, label_prefix, field):
        prefix = '{}.{}.{}.{}'.format(label_prefix, self.key, self.value,
                                      field)
        return prefix

    def append_children_bba(self, bba, label_prefix):
        for pin in self.pins:
            pin.append_children_bba(bba, self.field_label(
                label_prefix, 'pins'))

        bba.label(self.field_label(label_prefix, 'pins'), 'CellBelPinPOD')
        for pin in self.pins:
            pin.append_bba(bba, self.field_label(label_prefix, 'pins'))

    def append_bba(self, bba, label_prefix):
        bba.str_id(self.key)
        bba.str_id(self.value)
        bba.ref(self.field_label(label_prefix, 'pins'))
        bba.u32(len(self.pins))


class CellConstraint():
    def __init__(self):
        self.tag = None
        self.constraint_type = None
        self.states = []

    def field_label(self, label_prefix, field):
        prefix = '{}.{}.{}'.format(label_prefix, self.tag, field)
        return prefix

    def append_children_bba(self, bba, label_prefix):
        bba.label(self.field_label(label_prefix, 'states'), 'int32_t')
        for s in self.states:
            bba.u32(s)

    def append_bba(self, bba, label_prefix):
        bba.u32(self.tag)
        bba.u32(self.constraint_type.value)
        bba.ref(self.field_label(label_prefix, 'states'))
        bba.u32(len(self.states))


class CellBelMap():
    fields = ['common_pins', 'parameter_pins', 'constraints']
    field_types = ['CellBelPinPOD', 'ParameterPinsPOD', 'CellConstraintPOD']

    def __init__(self, cell, tile_type, site_index, bel):
        self.key = '_'.join((cell, tile_type, str(site_index), bel))
        self.common_pins = []
        self.parameter_pins = []
        self.constraints = []

    def field_label(self, label_prefix, field):
        prefix = '{}.{}.{}'.format(label_prefix, self.key, field)
        return prefix

    def append_children_bba(self, bba, label_prefix):
        for field in self.fields:
            for value in getattr(self, field):
                value.append_children_bba(
                    bba, self.field_label(label_prefix, field))

        for field, field_type in zip(self.fields, self.field_types):
            bba.label(self.field_label(label_prefix, field), field_type)
            for value in getattr(self, field):
                value.append_bba(bba, self.field_label(label_prefix, field))

    def append_bba(self, bba, label_prefix):
        for field in self.fields:
            bba.ref(self.field_label(label_prefix, field))
            bba.u32(len(getattr(self, field)))


class LutCell():
    def __init__(self):
        self.cell = ''
        self.input_pins = []
        self.parameter = ''

    def field_label(self, label_prefix, field):
        prefix = '{}.{}.{}'.format(label_prefix, self.cell, field)
        return prefix

    def append_children_bba(self, bba, label_prefix):
        bba.label(self.field_label(label_prefix, 'input_pins'), 'constids')
        for pin in self.input_pins:
            bba.str_id(pin)

    def append_bba(self, bba, label_prefix):
        bba.str_id(self.cell)
        bba.ref(self.field_label(label_prefix, 'input_pins'))
        bba.u32(len(self.input_pins))
        bba.str_id(self.parameter)


class CellParameter():
    def __init__(self):
        self.cell_type = ''
        self.parameter = ''
        self.format = 0
        self.default_value = ''

    def append_children_bba(self, bba, label_prefix):
        pass

    def append_bba(self, bba, label_prefix):
        bba.str_id(self.cell_type)
        bba.str_id(self.parameter)
        bba.u32(self.format)
        bba.str_id(self.default_value)


class CellMap():
    int_fields = ['cell_names', 'global_buffers', 'cell_bel_buckets']
    fields = ['cell_bel_map', 'lut_cells', 'cell_parameters']
    field_types = ['CellBelMapPOD', 'LutCellPOD', 'CellParameterPOD']

    def __init__(self):
        self.cell_names = []
        self.global_buffers = []
        self.cell_bel_buckets = []
        self.cell_bel_map = []
        self.lut_cells = []
        self.cell_parameters = []

    def add_cell(self, cell_name, cell_bel_bucket):
        self.cell_names.append(cell_name)
        self.cell_bel_buckets.append(cell_bel_bucket)

    def add_global_buffer_bel(self, bel_name):
        self.global_buffers.append(bel_name)

    def field_label(self, label_prefix, field):
        prefix = '{}.{}'.format(label_prefix, field)
        return prefix

    def append_children_bba(self, bba, label_prefix):
        assert len(self.cell_names) == len(self.cell_bel_buckets)

        for field in self.int_fields:
            bba.label(self.field_label(label_prefix, field), 'uint32_t')
            for s in getattr(self, field):
                bba.str_id(s)

        for field, field_type in zip(self.fields, self.field_types):
            for value in getattr(self, field):
                value.append_children_bba(
                    bba, self.field_label(label_prefix, field))

        for field, field_type in zip(self.fields, self.field_types):
            bba.label(self.field_label(label_prefix, field), field_type)
            for value in getattr(self, field):
                value.append_bba(bba, self.field_label(label_prefix, field))

    def append_bba(self, bba, label_prefix):
        assert len(self.cell_names) == len(self.cell_bel_buckets)

        for field in self.int_fields:
            bba.ref(self.field_label(label_prefix, field))
            bba.u32(len(self.cell_names))

        for field in self.fields:
            bba.ref(self.field_label(label_prefix, field))
            bba.u32(len(getattr(self, field)))


class PackagePin():
    def __init__(self):
        self.package_pin = ''
        self.site = ''
        self.bel = ''

    def append_children_bba(self, bba, label_prefix):
        pass

    def append_bba(self, bba, label_prefix):
        bba.str_id(self.package_pin)
        bba.str_id(self.site)
        bba.str_id(self.bel)


class Package():
    def __init__(self):
        self.package = ''
        self.package_pins = []

    def field_label(self, label_prefix, field):
        return '{}.{}.{}'.format(label_prefix, self.package, field)

    def append_children_bba(self, bba, label_prefix):
        for package_pin in self.package_pins:
            package_pin.append_children_bba(
                bba, self.field_label(label_prefix, 'package_pins'))

        bba.label(
            self.field_label(label_prefix, 'package_pins'), 'PackagePinPOD')
        for package_pin in self.package_pins:
            package_pin.append_bba(
                bba, self.field_label(label_prefix, 'package_pins'))

    def append_bba(self, bba, label_prefix):
        bba.str_id(self.package)
        bba.ref(self.field_label(label_prefix, 'package_pins'))
        bba.u32(len(self.package_pins))


class DefaultCellConnection():
    def __init__(self):
        self.name = ''
        self.value = 0

    def append_children_bba(self, bba, label_prefix):
        pass

    def append_bba(self, bba, label_prefix):
        bba.str_id(self.name)
        bba.u32(self.value)


class DefaultCellConnections():
    def __init__(self):
        self.cell_type = ''
        self.cell_pins = []

    def field_label(self, label_prefix, field):
        return '{}.{}.{}'.format(label_prefix, self.cell_type, field)

    def append_children_bba(self, bba, label_prefix):
        for cell_pin in self.cell_pins:
            cell_pin.append_children_bba(
                bba, self.field_label(label_prefix, 'cell_pins'))

        bba.label(
            self.field_label(label_prefix, 'cell_pins'),
            'DefaultCellConnectionPOD')
        for cell_pin in self.cell_pins:
            cell_pin.append_bba(bba, self.field_label(label_prefix,
                                                      'cell_pins'))

    def append_bba(self, bba, label_prefix):
        bba.str_id(self.cell_type)
        bba.ref(self.field_label(label_prefix, 'cell_pins'))
        bba.u32(len(self.cell_pins))


class Constants():
    def __init__(self):
        self.gnd_cell_name = ''
        self.gnd_cell_port = ''

        self.vcc_cell_name = ''
        self.vcc_cell_port = ''

        self.gnd_bel_tile = 0
        self.gnd_bel_index = 0
        self.gnd_bel_pin = ''

        self.vcc_bel_tile = 0
        self.vcc_bel_index = 0
        self.vcc_bel_pin = ''

        self.gnd_net_name = ''
        self.vcc_net_name = ''

        self.best_constant_net = ''

        self.default_conns = []

    def field_label(self, label_prefix, field):
        return '{}.constants.{}'.format(label_prefix, field)

    def append_children_bba(self, bba, label_prefix):
        for default_conn in self.default_conns:
            default_conn.append_children_bba(
                bba, self.field_label(label_prefix, 'default_conns'))

        bba.label(
            self.field_label(label_prefix, 'default_conns'),
            'DefaultCellConnectionsPOD')
        for default_conn in self.default_conns:
            default_conn.append_bba(
                bba, self.field_label(label_prefix, 'default_conns'))

    def append_bba(self, bba, label_prefix):
        bba.str_id(self.gnd_cell_name)
        bba.str_id(self.gnd_cell_port)

        bba.str_id(self.vcc_cell_name)
        bba.str_id(self.vcc_cell_port)

        bba.u32(self.gnd_bel_tile)
        bba.u32(self.gnd_bel_index)
        bba.str_id(self.gnd_bel_pin)

        bba.u32(self.vcc_bel_tile)
        bba.u32(self.vcc_bel_index)
        bba.str_id(self.vcc_bel_pin)

        bba.str_id(self.gnd_net_name)
        bba.str_id(self.vcc_net_name)

        bba.str_id(self.best_constant_net)

        bba.ref(self.field_label(label_prefix, 'default_conns'))
        bba.u32(len(self.default_conns))


class WireType():
    def __init__(self):
        self.name = ''
        self.category = 0

    def append_bba(self, bba, label_prefix):
        bba.str_id(self.name)
        bba.u32(self.category)

    def append_children_bba(self, bba, label_prefix):
        pass


class MacroParameter():
    def __init__(self):
        self.key = ''
        self.value = ''

    def append_children_bba(self, bba, label_prefix):
        pass

    def append_bba(self, bba, label_prefix):
        bba.str_id(self.key)
        bba.str_id(self.value)


class MacroParamRuleType(Enum):
    COPY = 0
    SLICE = 1
    TABLE = 2


class MacroParamMapRule():
    def __init__(self):
        self.prim_param = ''
        self.inst_name = ''
        self.inst_param = ''
        self.rule_type = 0,
        self.slice_bits = []
        self.map_table = []

    def field_label(self, label_prefix, field):
        return '{}.{}_{}_{}.{}'.format(label_prefix, self.prim_param,
                                       self.inst_name, self.inst_param, field)

    def append_children_bba(self, bba, label_prefix):
        for table_entry in self.map_table:
            table_entry.append_children_bba(
                bba, self.field_label(label_prefix, 'map_table'))

        bba.label(self.field_label(label_prefix, 'slice_bits'), 'uint32_t')
        for bit in self.slice_bits:
            bba.u32(bit)

        bba.label(
            self.field_label(label_prefix, 'map_table'), 'MacroParameterPOD')
        for table_entry in self.map_table:
            table_entry.append_bba(bba,
                                   self.field_label(label_prefix, 'map_table'))

    def append_bba(self, bba, label_prefix):
        bba.str_id(self.prim_param)
        bba.str_id(self.inst_name)
        bba.str_id(self.inst_param)
        bba.u32(self.rule_type)

        bba.ref(self.field_label(label_prefix, 'slice_bits'))
        bba.u32(len(self.slice_bits))
        bba.ref(self.field_label(label_prefix, 'map_table'))
        bba.u32(len(self.map_table))


class MacroCellInst():
    def __init__(self):
        self.name = ''
        self.type = ''
        self.parameters = []

    def field_label(self, label_prefix, field):
        return '{}.{}.{}'.format(label_prefix, self.name, field)

    def append_children_bba(self, bba, label_prefix):
        for param in self.parameters:
            param.append_children_bba(
                bba, self.field_label(label_prefix, 'parameters'))

        bba.label(
            self.field_label(label_prefix, 'parameters'), 'MacroParameterPOD')
        for param in self.parameters:
            param.append_bba(bba, self.field_label(label_prefix, 'parameters'))

    def append_bba(self, bba, label_prefix):
        bba.str_id(self.name)
        bba.str_id(self.type)
        bba.ref(self.field_label(label_prefix, 'parameters'))
        bba.u32(len(self.parameters))


class MacroPortInst():
    def __init__(self):
        self.instance = ''
        self.port = ''
        self.dir = 0

    def append_children_bba(self, bba, label_prefix):
        pass

    def append_bba(self, bba, label_prefix):
        bba.str_id(self.instance)
        bba.str_id(self.port)
        bba.u32(self.dir)


class MacroNet():
    def __init__(self):
        self.name = ''
        self.ports = []

    def field_label(self, label_prefix, field):
        return '{}.{}.{}'.format(label_prefix, self.name, field)

    def append_children_bba(self, bba, label_prefix):
        for port in self.ports:
            port.append_children_bba(bba,
                                     self.field_label(label_prefix, 'ports'))

        bba.label(self.field_label(label_prefix, 'ports'), 'MacroPortInstPOD')
        for port in self.ports:
            port.append_bba(bba, self.field_label(label_prefix, 'ports'))

    def append_bba(self, bba, label_prefix):
        bba.str_id(self.name)
        bba.ref(self.field_label(label_prefix, 'ports'))
        bba.u32(len(self.ports))


class Macro():
    def __init__(self):
        self.name = ''
        self.cell_insts = []
        self.nets = []

    def field_label(self, label_prefix, field):
        return '{}.{}.{}'.format(label_prefix, self.name, field)

    def append_children_bba(self, bba, label_prefix):
        for inst in self.cell_insts:
            inst.append_children_bba(
                bba, self.field_label(label_prefix, 'cell_insts'))
        for net in self.nets:
            net.append_children_bba(bba, self.field_label(
                label_prefix, 'nets'))

        bba.label(
            self.field_label(label_prefix, 'cell_insts'), 'MacroCellInstPOD')
        for inst in self.cell_insts:
            inst.append_bba(bba, self.field_label(label_prefix, 'cell_insts'))
        bba.label(self.field_label(label_prefix, 'nets'), 'MacroNetPOD')
        for net in self.nets:
            net.append_bba(bba, self.field_label(label_prefix, 'nets'))

    def append_bba(self, bba, label_prefix):
        bba.str_id(self.name)
        bba.ref(self.field_label(label_prefix, 'cell_insts'))
        bba.u32(len(self.cell_insts))
        bba.ref(self.field_label(label_prefix, 'nets'))
        bba.u32(len(self.nets))


class MacroExpansion():
    def __init__(self):
        self.prim_name = ''
        self.macro_name = ''
        self.param_matches = []
        self.param_rules = []

    def field_label(self, label_prefix, field):
        return '{}.{}_{}.{}'.format(label_prefix, self.prim_name,
                                    self.macro_name, field)

    def append_children_bba(self, bba, label_prefix):
        for param in self.param_matches:
            param.append_children_bba(
                bba, self.field_label(label_prefix, 'param_matches'))
        for rule in self.param_rules:
            rule.append_children_bba(
                bba, self.field_label(label_prefix, 'param_rules'))

        bba.label(
            self.field_label(label_prefix, 'param_matches'),
            'MacroParameterPOD')
        for param in self.param_matches:
            param.append_bba(bba,
                             self.field_label(label_prefix, 'param_matches'))
        bba.label(
            self.field_label(label_prefix, 'param_rules'),
            'MacroParamMapRulePOD')
        for rule in self.param_rules:
            rule.append_bba(bba, self.field_label(label_prefix, 'param_rules'))

    def append_bba(self, bba, label_prefix):
        bba.str_id(self.prim_name)
        bba.str_id(self.macro_name)
        bba.ref(self.field_label(label_prefix, 'param_matches'))
        bba.u32(len(self.param_matches))
        bba.ref(self.field_label(label_prefix, 'param_rules'))
        bba.u32(len(self.param_rules))


class GlobalCellPin():
    def __init__(self):
        self.name = ''
        self.max_hops = -1
        self.guide_placement = 0
        self.force_routing = 0

    def append_children_bba(self, bba, label_prefix):
        pass

    def append_bba(self, bba, label_prefix):
        bba.str_id(self.name)
        bba.u16(self.max_hops)
        bba.u8(self.guide_placement)
        bba.u8(self.force_routing)


class GlobalCell():
    def __init__(self):
        self.cell_type = ''
        self.pins = []

    def field_label(self, label_prefix, field):
        return '{}.{}.{}'.format(label_prefix, self.cell_type, field)

    def append_children_bba(self, bba, label_prefix):
        for cell_pin in self.pins:
            cell_pin.append_children_bba(
                bba, self.field_label(label_prefix, 'pins'))

        bba.label(self.field_label(label_prefix, 'pins'), 'GlobalCellPOD')
        for cell_pin in self.pins:
            cell_pin.append_bba(bba, self.field_label(label_prefix, 'pins'))

    def append_bba(self, bba, label_prefix):
        bba.str_id(self.cell_type)
        bba.ref(self.field_label(label_prefix, 'pins'))
        bba.u32(len(self.pins))


class ChipInfo():
    def __init__(self):
        self.name = ''
        self.generator = ''

        # Note: Increment by 1 this whenever schema changes.
        self.version = 10
        self.width = 0
        self.height = 0

        self.tile_types = []
        self.sites = []
        self.tiles = []
        self.nodes = []
        self.packages = []
        self.wire_types = []
        self.global_cells = []

        # str, constids
        self.bel_buckets = []

        self.cell_map = CellMap()
        self.constants = Constants()

        self.macros = []
        self.macro_rules = []

    def append_bba(self, bba, label_prefix):
        label = label_prefix

        children_fields = [
            'tile_types', 'sites', 'tiles', 'nodes', 'packages', 'wire_types',
            'global_cells', 'macros', 'macro_rules'
        ]
        children_types = [
            'TileTypeInfoPOD',
            'SiteInstInfoPOD',
            'TileInstInfoPOD',
            'NodeInfoPOD',
            'PackagePOD',
            'WireTypePOD',
            'GlobalCellPOD',
            'MacroPOD',
            'MacroExpansionPOD',
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

        struct_children_fields = ['cell_map', 'constants']
        struct_children_types = ['CellMapPOD', 'ConstantsPOD']

        for field, field_type in zip(struct_children_fields,
                                     struct_children_types):
            prefix = '{}.{}'.format(label, field)
            getattr(self, field).append_children_bba(bba, prefix)

            bba.label(prefix, field_type)
            getattr(self, field).append_bba(bba, prefix)

        bba.label(label, 'ChipInfoPOD')
        bba.str(self.name)
        bba.str(self.generator)
        bba.u32(self.version)
        bba.u32(self.width)
        bba.u32(self.height)

        for field in children_fields:
            bba.ref('{}.{}'.format(label, field))
            bba.u32(len(getattr(self, field)))

        bba.ref('{}.bel_buckets'.format(label))
        bba.u32(len(self.bel_buckets))

        for field in struct_children_fields:
            bba.ref('{}.{}'.format(label, field))

        bba.ref(self.strings_label(label))

    def strings_label(self, label_prefix):
        return '{}.constids'.format(label_prefix)
