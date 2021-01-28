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
""" Provides a FieldCache which caches data about a capnp struct field.

Because capnp structs are constant, and parsing the dynamic capnp data is
a non-trival operation, the FieldCache converts commonly accessed fields into
namedtuple's to avoid overhead.

"""
from collections import namedtuple

# List of scalar capnp types.
SCALAR_TYPES = [
    'bool',
    'int8',
    'int16',
    'int32',
    'int64',
    'uint8',
    'uint16',
    'uint32',
    'uint64',
    'float32',
    'float64',
    'text',
]

FieldProtoData = namedtuple(
    'FieldProtoData',
    'field_proto ref_annotation imp_annotation hide_field field_type field_which list_which schema_node_id'
)
ReferenceAnnotation = namedtuple('ReferenceAnnotation', 'type field depth')


def make_reference_annotation(annotation_value):
    """ Convert a reference annotation capnp message to a ReferenceAnnotation.
    """
    type = annotation_value.type
    field = annotation_value.field
    depth = None

    if type == 'parent':
        depth = annotation_value.depth

    return ReferenceAnnotation(type=type, field=field, depth=depth)


def make_field_proto(annotation_cache, schema_node_id, field_idx, field_proto):
    """ Convert a field proto message into a FieldProtoData object. """
    field_type = field_proto.slot.type
    field_which = field_type.which()

    ref_annotation = None
    imp_annotation = None
    hide_field = False
    for annotation_idx, annotation in enumerate(field_proto.annotations):
        _, annotation_value = annotation_cache.get_annotation_value(
            schema_node_id, field_idx, annotation_idx, annotation)
        if annotation_cache.is_reference_annotation(annotation):
            assert ref_annotation is None
            ref_annotation = make_reference_annotation(annotation_value)

        if annotation_cache.is_implementation_annotation(annotation):
            assert imp_annotation is None
            imp_annotation = annotation_value
            hide_field = imp_annotation.hide

    list_which = None
    schema_node_id = None
    if field_which == 'list':
        list_which = field_type.list.elementType.which()
        if list_which == 'struct':
            schema_node_id = field_type.list.elementType.struct.typeId
    elif field_which == 'struct':
        schema_node_id = field_type.struct.typeId

    return FieldProtoData(
        field_proto=field_proto,
        ref_annotation=ref_annotation,
        imp_annotation=imp_annotation,
        hide_field=hide_field,
        field_type=field_type,
        field_which=field_which,
        list_which=list_which,
        schema_node_id=schema_node_id)


class FieldData():
    """ Object to cache data about a field.

    Note: This cannot be a simple flat object in the event where the field
    is a union group.

    """

    def __init__(self, field_cache, field_index, field):
        self.field_cache = field_cache
        self.field_index = field_index
        self.field = field
        field_proto = field.proto
        self.key = field_proto.name
        self.which = field_proto.which()

        if self.which == 'group':
            self.field_proto = None
            self.group_protos = {}
        else:
            assert self.which == 'slot', self.which
            self.field_proto = make_field_proto(
                annotation_cache=self.field_cache.annotation_cache,
                schema_node_id=self.field_cache.schema_node_id,
                field_idx=field_index,
                field_proto=field_proto,
            )
            self.group_protos = None

    def get_field_proto(self):
        """ Return field proto data when which == 'slot'. """
        return self.field_proto

    def get_group_proto(self, inner_key):
        """ Return group field proto data when which == 'group'. """
        group_proto = self.group_protos.get(inner_key, None)
        if group_proto is None:
            group_proto = self.field.schema.fields[inner_key].proto
            self.group_protos[inner_key] = make_field_proto(
                annotation_cache=self.field_cache.annotation_cache,
                schema_node_id=self.field_cache.schema_node_id,
                field_idx=self.field_index,
                field_proto=group_proto,
            )

        return self.group_protos[inner_key]


class FieldCache():
    """ Provides field data caching for a specific message schema. """

    def __init__(self, annotation_cache, schema):
        self.annotation_cache = annotation_cache
        self.schema = schema
        self.schema_node_id = schema.node.id
        self.has_union_fields = bool(schema.union_fields)
        self.field_data = {}
        self.base_fields = set(schema.non_union_fields)
        self.union_fields = set(schema.union_fields)
        self.fields_list = []

        for idx, field in enumerate(schema.fields_list):
            self.fields_list.append(FieldData(self, idx, field))

    def fields(self, struct_reader):
        """ Return list of fields in specified message reader. """
        if self.has_union_fields:
            fields = set(self.base_fields)
            fields.add(struct_reader.which())
            return fields
        else:
            return self.base_fields

    def get_reader_fields(self, input_fields):
        """ Return information to build message from list of input_fields.


        Returns:
            fields - List of all fields in output.
            defered_fields - Map of fields to defer and their implemenation
                annotation.
            union_field - Which field (if any) is a union field that needs
                special handling.

        """
        fields = set(self.base_fields)
        defered_fields = {}

        union_field = None
        for field in self.union_fields:
            if field in input_fields:
                assert union_field is None, (field, union_field)
                union_field = field
                fields.add(field)

        for field_data in self.fields_list:
            key = field_data.key
            if key not in fields:
                continue

            which = field_data.which
            if which != 'slot':
                continue

            if field_data.field_proto.imp_annotation is not None:
                defered_fields[key] = field_data.field_proto.imp_annotation

        return fields, defered_fields, union_field
