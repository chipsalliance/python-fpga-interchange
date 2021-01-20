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
""" Defines some utility functions for inspecting capnp annotations.

get_annotation_value is generic to any capnp file.

get_first_enum_field_display_name and AnnotationCache are both specific
to the annotations used in the FPGA interchange capnp format.

"""
from fpga_interchange.capnp_utils import get_module_from_id


def get_first_enum_field_display_name(annotation_value, parser=None):
    """ Returns the displayName of annotations of a specific structure.

    All annotations used for FPGA interchange capnp file annotations have
    an enum as the first field.  This functions returns the displayName of the
    supplied annotation_value, if and only if the first field of the
    annotation_value is an enum.

    The parser argument is optional, as the default parser is the global
    parser defined by pycapnp.  In the event that the annotation in question
    was not parsed by this parser, that parser should be supplied.
    This case should be rare.

    """

    field0_proto = annotation_value.schema.fields_list[0].proto
    if field0_proto.which() != 'slot':
        return None

    field0_type = field0_proto.slot.type
    if field0_type.which() != 'enum':
        return None

    e = get_module_from_id(field0_type.enum.typeId, parser)
    return e.schema.node.displayName


def get_annotation_value(annotation, parser=None):
    """ Get annotation value from an annotation.  Schema that the annotation belongs too is required. """

    annotation_module = get_module_from_id(annotation.id, parser)
    name = annotation_module.__name__

    which = annotation.value.which()
    if which == 'struct':
        annotation_type = annotation_module._nodeSchema.node.annotation.type

        assert annotation_type.which() == 'struct'
        struct_type_id = annotation_type.struct.typeId
        annotation_struct_type = get_module_from_id(struct_type_id, parser)
        return name, annotation.value.struct.as_struct(annotation_struct_type)
    elif which == 'void':
        return name, None
    elif which in [
            'bool', 'float32', 'float64', 'int16', 'int32', 'int64', 'int8',
            'text', 'uint16', 'uint32', 'uint64', 'uint8'
    ]:
        return name, getattr(annotation.value, which)
    else:
        raise NotImplementedError(
            'Annotation of type {} not supported yet.'.format(which))


class AnnotationCache():
    """ Cache for annotation values and display names.

    Because parsing annotation values requires non-trival operations to
    inspect, it is useful to provide a simple cache of annotations based on a
    structural key.

    In this case the structural key is:
     - node_id - The unique id supplied to the capnp struct the annotation
                 comes from.
     - field_idx - The field number that the annotation applies too.
     - annotation_idx - The index into the annotations list.

    It is believed that the above 3-tuple uniquely specifies an annotation in
    a schema.

    """

    def __init__(self, parser=None):
        self.parser = parser

        self.annotation_values = {}
        self.annotation_display_names = {}

    def get_annotation_value(self, node_id, field_idx, annotation_idx,
                             annotation):
        """ Get the annotation value for the specified annotation at the specified key. """
        key = (node_id, field_idx, annotation_idx)
        if key not in self.annotation_values:
            self.annotation_values[key] = get_annotation_value(
                annotation, self.parser)

        return self.annotation_values[key]

    def is_first_field_display_name(self, annotation, expected_display_name):
        """ See if the annotation displayName supplied matches the expected_display_name. """
        if annotation.id not in self.annotation_display_names:
            _, annotation_value = get_annotation_value(annotation, self.parser)
            self.annotation_display_names[
                annotation.id] = get_first_enum_field_display_name(
                    annotation_value, self.parser)

        display_name = self.annotation_display_names[annotation.id]
        if display_name is None:
            return False
        return display_name == expected_display_name

    def is_reference_annotation(self, annotation):
        """ Is the annotation a FPGA interchange text reference annotation? """
        return self.is_first_field_display_name(
            annotation, 'References.capnp:ReferenceType')

    def is_implementation_annotation(self, annotation):
        """ Is the annotation a FPGA interchange text impl annotation? """
        return self.is_first_field_display_name(
            annotation, 'References.capnp:ImplementationType')
