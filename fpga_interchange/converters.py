#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright (C) 2020  The SymbiFlow Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
""" Implements generic text format conversion using abstract writer and reader classes.

When implementing a new text format, both the AbstractWriter and AbstractReader
should be implemented.  If implemented properly, to_writer and from_reader
should be able to round-trip any FPGA interchange from the text format to
and from the capnp format.

"""
from fpga_interchange.annotations import AnnotationCache
from fpga_interchange.field_cache import FieldCache, SCALAR_TYPES


class Enumerator():
    """ Enumerator implementation for emumeration implemented fields.

    Provides a two way mapping between a value and an index.  List of values
    can be written to disk with write_message method.

    """

    def __init__(self):
        self.values = []
        self.map = {}

    def add(self, value):
        assert value not in self.map
        self.get_index(value)

    def get(self, index):
        return self.values[index]

    def get_index(self, value):
        index = self.map.get(value, None)
        if index is None:
            self.values.append(value)
            index = len(self.values) - 1
            self.map[value] = index

        return index

    def write_message(self, message, field):
        list_builder = message.init(field, len(self.values))

        for idx, value in enumerate(self.values):
            list_builder[idx] = value


def init_implementation(annotation_value):
    """ In a field implementation based on the implementation annotation. """
    if annotation_value.type == 'enumerator':
        return Enumerator()
    else:
        raise NotImplementedError()


class BaseReaderWriter():
    def __init__(self, parent):
        self.parent = parent
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


class AbstractWriter(BaseReaderWriter):
    """ Abstract writer class to be implemented to add a text format for the FPGA
    interchange.  All methods are required.

    Arguments:
        struct_reader (capnp Reader): Reader object
        parent: Either None if this instance is the root writer, or the parent
            object of this AbstractWriter.

    """

    def __init__(self, struct_reader, parent):
        super().__init__(parent)

    def set_value_inner_key(self, key, inner_key, which, value):
        """ Sets the value of a group field inner value.

        This is used when setting the value on a group field.

        which (str) - What is the capnp type of value being set.  Is a
            SCALAR_TYPES, 'enum', or, 'struct'.

        For a simple map implementation, this would look like:

        >>> obj = {}
        >>> key = 'outer'
        >>> inner_key = 'inner'
        >>> value = 'value'
        >>> obj.update({key: {inner_key: value}})

        """
        raise NotImplementedError("set_value_inner_key unimplemented.")

    def set_value(self, key, which, value):
        """ Sets the value of a field.

        which (str) - What is the capnp type of value being set.  Is a
            SCALAR_TYPES, 'enum', or, 'struct'.

        For a simple map implementation, this would look like:

        >>> obj = {}
        >>> key = 'key'
        >>> value = 'value'
        >>> obj[key] = value

        """
        raise NotImplementedError("set_value unimplemented.")

    def dereference_value(self, ref_annotation, value, root, parent):
        """ Dereference the specified value per the reference annotation.

        This dereference should result in the same reference_value being
        returned if the text format's AbstractReader is used.

        """
        raise NotImplementedError("dereference_value unimplemented.")

    def make_list(self):
        """ Create a list in the text format, and return an object.

        The object returned will be passed to append_to_list's first argumnet.

        """
        raise NotImplementedError("make_list unimplemented.")

    def append_to_list(self, list_obj, which, value):
        """ Append a value to a list that was created with make_list. """
        raise NotImplementedError("append_to_list unimplemented.")

    def output(self):
        """ """
        raise NotImplementedError("output unimplemented.")


class AbstractReader(BaseReaderWriter):
    """ Abstract reader class to be implemented to add a text format for the
    FPGA interchange.  All methods are required.

    Arguments:
        data: Data being read at this level of the structure.
        parent: Either None if this instance is the root writer, or the parent
            object of this AbstractReader.

    """

    def __init__(self, data, parent):
        super().__init__(parent)
        self.objects = {}

    def init_object(self, key, value):
        """ Initiailize a field that have a implementation annotation. """
        self.objects[key] = value

    def get_object(self, key):
        """ Get a field object that has a implementation annotation. """
        return self.objects[key]

    def keys(self):
        """ Return list of field keys at this level of data.

        For a simple map implementation, this would look like:

        >>> obj = {'outer': {'inner': 'value'}}
        >>> keys = obj.keys()

        """
        raise NotImplementedError("keys unimplemented.")

    def get_field_keys(self, key):
        """ Return list of field keys for a specific key at this level of data.

        For a simple map implementation, this would look like:

        >>> obj = {'outer': {'inner': 'value'}}
        >>> key = 'outer'
        >>> keys = obj['outer'].keys()

        """
        raise NotImplementedError("get_field_keys unimplemented.")

    def get_inner_field(self, key, inner_key):
        """ Return value from an inner field.

        For a simple map implementation, this would look like:

        >>> obj = {'outer': {'inner': 'value'}}
        >>> key = 'outer'
        >>> inner_key = 'inner'
        >>> value = obj[key][inner_key]

        The return value from this method will be passed to
        AbstractReader.read_scalar or to AbstractReader.__init__ per the
        schema.

        """
        raise NotImplementedError("get_inner_field unimplemented.")

    def get_field(self, key):
        """ Return value from a field.

        For a simple map implementation, this would look like:

        >>> obj = {'outer': {'inner': 'value'}}
        >>> key = 'outer'
        >>> value = obj[key]

        The return value from this method will be passed to
        AbstractReader.read_scalar or to AbstractReader.__init__ per the
        schema.

        """
        raise NotImplementedError("get_inner_field unimplemented.")

    def reference_value(self, ref_annotation, value, root, parent):
        """ Return the reference value originally passed to
        AbstractWriter.dereference_value.

        """
        raise NotImplementedError("reference_value unimplemented.")

    def read_scalar(self, which, value):
        """ Convert a scalar from raw data to a format that matches the which.

        which (str): The scalar value expected by the capnp structure.
        value: The raw value returned by get_field / get_inner_field.

        For formats where data conversion is required (e.g. raw data is all
        strings), apply required conversions as needed.

        For example, if the text format lacks a first class null/None object,
        convert from textual formats approximation to None.

        """
        raise NotImplementedError("read_scalar unimplemented.")


def to_writer(struct_reader,
              writer_class,
              root=None,
              parent=None,
              annotation_cache=None,
              schema_node_id=None):
    """ Convert a FPGA interchange message to a textual format, as defined by writer_class.

    struct_reader (capnp Reader): Capnp message to be converted.
    writer_class - AbstractWriter implementation.

    Returns writer_class output method.

    """
    writer = writer_class(struct_reader, parent)
    assert isinstance(writer, AbstractWriter)

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
    """ Convert to a FPGA interchange message from a textual format, as defined by reader class.

    message - Message to be populated from data.
    data - Textual format to be converted.
    reader_class - AbstractReader implementation.

    Returns writer_class output method.

    """
    reader = reader_class(data, parent)
    assert isinstance(reader, AbstractReader)

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
        reader.init_object(key, init_implementation(annotation_value))

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
        reader.get_object(field).write_message(message, field)
