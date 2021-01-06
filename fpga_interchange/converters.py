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
from fpga_interchange.annotations import AnnotationCache




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


class YamlWriter():
    def __init__(self, struct_reader, parent):
        self.out = {}
        self.struct_reader = struct_reader
        self.parent = parent

    def get_parent(self, depth):
        if depth == 0:
            return self
        else:
            return self.parent.get_parent(depth-1)

    def dereference_value(self, annotation_type, value, root_writer, parent_writer):
        if annotation_type.type == 'root':
            return root_writer.out[annotation_type.field][value]
        elif annotation_type.type == 'rootValue':
            return getattr(root_writer.struct_reader, annotation_type.field)[value]
        else:
            assert annotation_type.type == 'parent'
            return self.get_parent(annotation_type.depth).out[annotation_type.field][value]

    def set_value(self, key, value):
        self.out[key] = value

    def set_value_inner_key(self, key, inner_key, value):
        self.out.update({key: {inner_key: value}})

    def make_list(self):
        return []

    def append_to_list(self, l, value):
        l.append(value)

    def output(self):
        return self.out


class JsonWriter():
    def __init__(self, struct_reader, parent):
        self.out = {}
        self.struct_reader = struct_reader
        self.next_id = 0
        self.obj_id_cache = {}
        self.parent = parent

    def get_parent(self, depth):
        if depth == 0:
            return self
        else:
            return self.parent.get_parent(depth-1)

    def get_object_with_id(self, field, value):
        item = self.out[field][value]

        if id(item) not in self.obj_id_cache:
            self.obj_id_cache[id(item)] = self.next_id
            self.next_id += 1

        item_id = self.obj_id_cache[id(item)]

        if '_id' not in item:
            item['_id'] = item_id
        else:
            assert item['_id'] == item_id, (
                item['_id'],
                item_id,
                )

        return item

    def dereference_value(self, annotation_type, value, root_writer, parent_writer):
        if annotation_type.type == 'root':
            return root_writer.get_object_with_id(annotation_type.field, value)
        elif annotation_type.type == 'rootValue':
            return getattr(root_writer.struct_reader, annotation_type.field)[value]
        else:
            assert annotation_type.type == 'parent'
            return self.get_parent(annotation_type.depth).get_object_with_id(annotation_type.field, value)

    def set_value(self, key, value):
        self.out[key] = value

    def set_value_inner_key(self, key, inner_key, value):
        self.out.update({key: {inner_key: value}})

    def make_list(self):
        return []

    def append_to_list(self, l, value):
        l.append(value)

    def output(self):
        return self.out


def to_writer(struct_reader, writer_class, root=None, parent=None, annotation_cache=None):
    writer = writer_class(struct_reader, parent)
    if root is None:
        root = writer

    if annotation_cache is None:
        annotation_cache = AnnotationCache()

    schema = struct_reader.schema
    schema_node_id = schema.node.id

    fields = set(schema.non_union_fields)
    if schema.union_fields:
        fields.add(struct_reader.which())

    for field_idx, field in enumerate(schema.fields_list):
        key = field.proto.name
        if key not in fields:
            continue

        which = field.proto.which()
        if which == 'group':
            group = getattr(struct_reader, key)
            inner_key = group.which()
            value = getattr(group, inner_key)

            set_value = lambda value: writer.set_value_inner_key(key, inner_key, value)
            field_proto = field.schema.fields[inner_key].proto
        else:
            assert which == 'slot', which
            value = getattr(struct_reader, key)
            set_value = lambda value: writer.set_value(key, value)
            field_proto = field.proto

        deference_fun = None
        hide_field = False
        for annotation_idx, annotation in enumerate(field_proto.annotations):
            _, annotation_value = annotation_cache.get_annotation_value(
                schema_node_id, field_idx, annotation_idx, annotation)
            if annotation_cache.is_reference_annotation(annotation):
                assert deference_fun is None
                deference_fun = lambda value: writer.dereference_value(annotation_value, value, root, parent)

            if annotation_cache.is_implementation_annotation(annotation):
                if annotation_value.hide:
                    hide_field = True

        if hide_field:
            continue

        if deference_fun is None:
            deference_fun = lambda value: value

        field_type = field_proto.slot.type

        field_which = field_type.which()
        if field_which == 'struct':
            set_value(to_writer(value, writer_class, root=root, parent=writer, annotation_cache=annotation_cache))
        elif field_which == 'list':
            list_type = field_type.list.elementType
            list_which = list_type.which()

            data = writer.make_list()
            if list_which == 'struct':
                for elem in value:
                    writer.append_to_list(data, to_writer(elem, writer_class, root=root, parent=writer, annotation_cache=annotation_cache))
            else:
                for elem in value:
                    writer.append_to_list(data, deference_fun(elem))

            set_value(data)
        elif field_which == 'void':
            set_value(None)
        elif field_which == 'enum':
            set_value(value._as_str())
        else:
            assert field_which in SCALAR_TYPES, field_which

            set_value(deference_fun(value))

    return writer.output()


def to_yaml(struct_reader):
    return to_writer(struct_reader, YamlWriter)


def to_json(struct_reader):
    return to_writer(struct_reader, JsonWriter)


class IndexCache():
    def __init__(self, data):
        self.data = data
        self.caches = {}

    def get_index(self, field, value):
        if field not in self.caches:
            self.caches[field] = {}
            for idx, obj in enumerate(self.data[field]):
                self.caches[field][id(obj)] = idx

        return self.caches[field][id(value)]


class YamlReader():
    def __init__(self, message, data, parent):
        self.message = message
        self.data = data
        self.objects = {}
        self.index_cache = IndexCache(self.data)
        self.parent = parent

    def get_parent(self, depth):
        if depth == 0:
            return self
        else:
            return self.parent.get_parent(depth-1)

    def get_index(self, field, value):
        return self.index_cache.get_index(field, value)

    def reference_value(self, annotation_type, value, root_reader, parent_reader):
        if annotation_type.type == 'root':
            return root_reader.get_index(annotation_type.field, value)
        elif annotation_type.type == 'rootValue':
            return root_reader.objects[annotation_type.field].get_index(value)
        else:
            assert annotation_type.type == 'parent'
            return self.get_parent(annotation_type.depth).get_index(annotation_type.field, value)


class JsonIndexCache():
    def __init__(self, data):
        self.data = data
        self.caches = {}

    def get_index(self, field, value):
        if field not in self.caches:
            self.caches[field] = {}
            for idx, obj in enumerate(self.data[field]):
                self.caches[field][obj['_id']] = idx

        return self.caches[field][value['_id']]


class JsonReader():
    def __init__(self, message, data, parent):
        self.message = message
        self.data = data
        self.objects = {}
        self.index_cache = JsonIndexCache(self.data)
        self.parent = parent

    def get_parent(self, depth):
        if depth == 0:
            return self
        else:
            return self.parent.get_parent(depth-1)

    def get_index(self, field, value):
        return self.index_cache.get_index(field, value)

    def reference_value(self, annotation_type, value, root_reader, parent_reader):
        if annotation_type.type == 'root':
            return root_reader.get_index(annotation_type.field, value)
        elif annotation_type.type == 'rootValue':
            return root_reader.objects[annotation_type.field].get_index(value)
        else:
            assert annotation_type.type == 'parent'
            return self.get_parent(annotation_type.depth).get_index(annotation_type.field, value)

def from_reader(message, data, reader_class, root=None, parent=None, annotation_cache=None):
    reader = reader_class(message, data, parent)
    if root is None:
        root = reader

    if annotation_cache is None:
        annotation_cache = AnnotationCache()

    schema = message.schema
    schema_node_id = schema.node.id

    fields = set(schema.non_union_fields)
    defered_fields = set()

    union_field = None
    for field in schema.union_fields:
        if field in data:
            assert union_field is None, (field, union_field)
            union_field = field
            fields.add(field)

    for field_idx, field in enumerate(schema.fields_list):
        key = field.proto.name
        if key not in fields:
            continue

        which = field.proto.which()
        if which != 'slot':
            continue

        for annotation_idx, annotation in enumerate(field.proto.annotations):
            _, annotation_value = annotation_cache.get_annotation_value(
                schema_node_id, field_idx, annotation_idx, annotation)
            if annotation_cache.is_implementation_annotation(annotation):
                if annotation_value.hide:
                    reader.objects[key] = init_implementation(annotation_value)
                    defered_fields.add(key)

    for field in defered_fields:
        assert field not in data

    for field_idx, field in enumerate(schema.fields_list):
        key = field.proto.name
        if key not in fields or key in defered_fields:
            continue

        which = field.proto.which()
        if which == 'group':
            keys = list(data[key].keys())
            assert len(keys) == 1, keys
            inner_key = keys[0]
            builder = getattr(message, key)
            field_data = data[key][inner_key]
            key = inner_key
            field_proto = field.schema.fields[inner_key].proto
        else:
            builder = message
            field_data = data[key]
            field_proto = field.proto

        reference_fun = None
        hide_field = False
        for annotation_idx, annotation in enumerate(field_proto.annotations):
            _, annotation_value = annotation_cache.get_annotation_value(
                schema_node_id, field_idx, annotation_idx, annotation)
            if annotation_cache.is_reference_annotation(annotation):
                assert reference_fun is None
                reference_fun = lambda value: reader.reference_value(annotation_value, value, root, parent)

            if annotation_cache.is_implementation_annotation(annotation):
                if annotation_value.hide:
                    hide_field = True

        if reference_fun is None:
            reference_fun = lambda value: value

        if hide_field:
            continue

        field_type = field_proto.slot.type
        field_which = field_type.which()
        if field_which == 'struct':
            builder.init(key)
            from_reader(
                message=getattr(builder, key),
                data=field_data,
                reader_class=reader_class,
                root=root,
                parent=reader,
                annotation_cache=annotation_cache)
        elif field_which == 'list':
            list_builder = builder.init(key, len(field_data))
            list_type = field_type.list.elementType
            list_which = list_type.which()

            if list_which == 'struct':
                for elem_builder, elem in zip(list_builder, field_data):
                    from_reader(
                        message=elem_builder,
                        data=elem,
                        reader_class=reader_class,
                        root=root,
                        parent=reader,
                        annotation_cache=annotation_cache)
            else:
                for idx, elem in enumerate(field_data):
                    list_builder[idx] = reference_fun(elem)
        elif field_which == 'void':
            assert field_data is None
            setattr(builder, key, None)
        elif field_which == 'enum':
            setattr(builder, key, field_data)
        else:
            assert field_which in SCALAR_TYPES, field_which

            setattr(builder, key, reference_fun(field_data))

    for field in defered_fields:
        reader.objects[field].write_message(message, field)

def from_yaml(message, data):
    from_reader(message, data, YamlReader)

def from_json(message, data):
    from_reader(message, data, JsonReader)
