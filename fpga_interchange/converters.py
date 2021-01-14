#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright (C) 2020  The SymbiFlow Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
from fpga_interchange.annotations import AnnotationCache
from fpga_interchange.field_cache import FieldCache, SCALAR_TYPES


class Enumerator():
    def __init__(self):
        self.values = []
        self.map = {}

    def get_index(self, value):
        index = self.map.get(value, None)
        if index is None:
            self.values.append(value)
            return len(self.values) - 1
        else:
            return index

    def write_message(self, message, field):
        list_builder = message.init(field, len(self.values))

        for idx, value in enumerate(self.values):
            list_builder[idx] = value


def init_implementation(annotation_value):
    if annotation_value.type == 'enumerator':
        return Enumerator()
    else:
        raise NotImplementedError()


class BaseReaderWriter():
    def __init__(self):
        self.field_cache = {}
        self.value_cache = {}

    def get_field_value(self, field, value):
        if field not in self.value_cache:
            self.value_cache[field] = [
                v for v in getattr(self.struct_reader, field)
            ]

        return self.value_cache[field][value]

    def get_parent(self, depth):
        if depth == 0:
            return self
        else:
            return self.parent.get_parent(depth - 1)

    def get_field_cache(self, annotation_cache, schema, schema_node_id):
        if schema_node_id not in self.field_cache:
            self.field_cache[schema_node_id] = FieldCache(
                annotation_cache, schema)
        return self.field_cache[schema_node_id]


def to_writer(struct_reader,
              writer_class,
              root=None,
              parent=None,
              annotation_cache=None,
              schema_node_id=None):
    writer = writer_class(struct_reader, parent)
    if root is None:
        root = writer

    if annotation_cache is None:
        annotation_cache = AnnotationCache()

    schema = struct_reader.schema
    if schema_node_id is None:
        schema_node_id = schema.node.id

    field_cache = root.get_field_cache(annotation_cache, schema,
                                       schema_node_id)

    fields = field_cache.fields(struct_reader)

    for field_idx, field in enumerate(field_cache.fields_list):
        key = field.key
        if key not in fields:
            continue

        which = field.which
        if which == 'group':
            group = getattr(struct_reader, key)
            inner_key = group.which()
            value = getattr(group, inner_key)

            set_value = lambda value_which, value: writer.set_value_inner_key(key, inner_key, value_which, value)
            field_proto_data = field.get_group_proto(inner_key)
        else:
            assert which == 'slot', which
            value = getattr(struct_reader, key)
            set_value = lambda value_which, value: writer.set_value(key, value_which, value)
            field_proto_data = field.get_field_proto()

        if field_proto_data.ref_annotation is not None:
            deference_fun = lambda value: writer.dereference_value(field_proto_data.ref_annotation, value, root, parent)
        else:
            deference_fun = lambda value: value

        if field_proto_data.hide_field:
            continue

        field_which = field_proto_data.field_which
        if field_which == 'struct':
            set_value(
                field_which,
                to_writer(
                    value,
                    writer_class,
                    root=root,
                    parent=writer,
                    annotation_cache=annotation_cache,
                    schema_node_id=field_proto_data.schema_node_id,
                ))
        elif field_which == 'list':
            list_which = field_proto_data.list_which

            data = writer.make_list()
            if list_which == 'struct':
                for elem in value:
                    writer.append_to_list(
                        data, list_which,
                        to_writer(
                            elem,
                            writer_class,
                            root=root,
                            parent=writer,
                            annotation_cache=annotation_cache,
                            schema_node_id=field_proto_data.schema_node_id))
            else:
                for elem in value:
                    writer.append_to_list(data, list_which,
                                          deference_fun(elem))

            set_value(field_which, data)
        elif field_which == 'void':
            set_value(field_which, None)
        elif field_which == 'enum':
            set_value(field_which, value._as_str())
        else:
            assert field_which in SCALAR_TYPES, field_which

            set_value(field_which, deference_fun(value))

    return writer.output()


def from_reader(message,
                data,
                reader_class,
                root=None,
                parent=None,
                annotation_cache=None,
                schema_node_id=None):
    reader = reader_class(message, data, parent)
    if root is None:
        root = reader

    if annotation_cache is None:
        annotation_cache = AnnotationCache()

    schema = message.schema
    if schema_node_id is None:
        schema_node_id = schema.node.id

    field_cache = root.get_field_cache(annotation_cache, schema,
                                       schema_node_id)

    fields, defered_fields, union_field = field_cache.get_reader_fields(
        reader.keys())

    for key, annotation_value in defered_fields.items():
        reader.objects[key] = init_implementation(annotation_value)

    for field_idx, field in enumerate(field_cache.fields_list):
        key = field.key
        if key not in fields or key in defered_fields:
            continue

        which = field.which
        if which == 'group':
            keys = list(reader.get_field_keys(key))
            assert len(keys) == 1, keys
            inner_key = keys[0]
            builder = getattr(message, key)
            field_data = reader.get_inner_field(key, inner_key)
            key = inner_key
            field_proto_data = field.get_group_proto(inner_key)
        else:
            builder = message
            field_data = reader.get_field(key)
            field_proto_data = field.get_field_proto()

        if field_proto_data.hide_field:
            continue

        if field_proto_data.ref_annotation is not None:
            reference_fun = lambda value: reader.reference_value(field_proto_data.ref_annotation, value, root, parent)
        else:
            reference_fun = lambda value: value

        field_which = field_proto_data.field_which
        if field_which == 'struct':
            builder.init(key)
            from_reader(
                message=getattr(builder, key),
                data=field_data,
                reader_class=reader_class,
                root=root,
                parent=reader,
                annotation_cache=annotation_cache,
                schema_node_id=field_proto_data.schema_node_id)
        elif field_which == 'list':
            list_builder = builder.init(key, len(field_data))
            list_which = field_proto_data.list_which

            if list_which == 'struct':
                for elem_builder, elem in zip(list_builder, field_data):
                    from_reader(
                        message=elem_builder,
                        data=elem,
                        reader_class=reader_class,
                        root=root,
                        parent=reader,
                        annotation_cache=annotation_cache,
                        schema_node_id=field_proto_data.schema_node_id)
            else:
                for idx, elem in enumerate(field_data):
                    value = reference_fun(elem)
                    list_builder[idx] = reader.read_scalar(list_which, value)
        elif field_which == 'void':
            assert field_data is None
            setattr(builder, key, None)
        elif field_which == 'enum':
            setattr(builder, key, field_data)
        else:
            assert field_which in SCALAR_TYPES, field_which

            value = reference_fun(field_data)
            value = reader.read_scalar(field_which, value)
            setattr(builder, key, value)

    for field in defered_fields:
        reader.objects[field].write_message(message, field)
