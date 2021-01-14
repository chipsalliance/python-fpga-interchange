#/usr/bin/env python3
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
from fpga_interchange.field_cache import FieldCache, SCALAR_TYPES


class CompareCapnp():
    def __init__(self, unittest, root1, root2):
        self.annotation_cache = AnnotationCache()
        self.unittest = unittest
        self.root1 = root1
        self.root2 = root2
        self.field_cache = {}
        self.value_cache1 = {}
        self.value_cache2 = {}

    def get_field_cache(self, schema, schema_node_id):
        if schema_node_id not in self.field_cache:
            self.field_cache[schema_node_id] = FieldCache(self.annotation_cache, schema)
        return self.field_cache[schema_node_id]

    def dereference_value(self, annotation, value1, value2):
        if annotation is None:
            return value1, value2

        if annotation.type != 'rootValue':
            return value1, value2

        field = annotation.field
        if field not in self.value_cache1:
            self.value_cache1[field] = [v for v in getattr(self.root1, field)]
            self.value_cache2[field] = [v for v in getattr(self.root2, field)]

        value1 = self.value_cache1[field][value1]
        value2 = self.value_cache2[field][value2]

        return value1, value2

    def compare_capnp(self, schema_node_id, message1, message2, field_lists=[]):
        field_cache = self.get_field_cache(message1.schema, schema_node_id)

        fields1 = field_cache.fields(message1)
        fields2 = field_cache.fields(message2)

        self.unittest.assertEqual(fields1, fields2, msg=str(field_lists))

        orig_field_lists = field_lists

        for field_idx, field in enumerate(field_cache.fields_list):
            key = field.key
            if key not in fields1:
                continue

            field_lists = list(orig_field_lists)
            field_lists.append(key)

            which = field.which
            if which == 'group':
                group1 = getattr(message1, key)
                group2 = getattr(message2, key)

                inner_key1 = group1.which()
                inner_key2 = group1.which()
                self.unittest.assertEqual(inner_key1, inner_key2, msg=str(field_lists))

                field_lists.append(inner_key1)
                value1 = getattr(group1, inner_key1)
                value2 = getattr(group2, inner_key2)

                field_proto_data = field.get_group_proto(inner_key1)
            else:
                assert which == 'slot', which
                value1 = getattr(message1, key)
                value2 = getattr(message2, key)

                field_proto_data = field.get_field_proto()

            if field_proto_data.hide_field:
                continue

            field_which = field_proto_data.field_which
            if field_which == 'struct':
                self.compare_capnp(
                    schema_node_id=field_proto_data.schema_node_id,
                    message1=value1,
                    message2=value2,
                    field_lists=field_lists)
            elif field_which == 'list':
                list_which = field_proto_data.list_which

                field_lists.append(0)

                if list_which == 'struct':
                    for idx, (elem1, elem2) in enumerate(zip(value1, value2)):
                        field_lists[-1] = idx
                        self.compare_capnp(
                            schema_node_id=field_proto_data.schema_node_id,
                            message1=elem1,
                            message2=elem2,
                            field_lists=field_lists)
                else:
                    for idx, (elem1, elem2) in enumerate(zip(value1, value2)):
                        field_lists[-1] = idx
                        elem1, elem2 = self.dereference_value(field_proto_data.ref_annotation, elem1, elem2)
                        self.unittest.assertEqual(elem1, elem2, msg=str(field_lists))
            elif field_which == 'void':
                pass
            elif field_which == 'enum':
                self.unittest.assertEqual(value1, value2, msg=str(field_lists))
            else:
                assert field_which in SCALAR_TYPES, field_which

                value1, value2 = self.dereference_value(field_proto_data.ref_annotation, value1, value2)
                self.unittest.assertEqual(value1, value2, msg=str(field_lists))


def compare_capnp(unittest, message1, message2):
    schema_node_id = message1.schema.node.id

    unittest.assertEqual(schema_node_id, message2.schema.node.id)

    comp = CompareCapnp(unittest, message1, message2)
    comp.compare_capnp(schema_node_id, message1, message2)
