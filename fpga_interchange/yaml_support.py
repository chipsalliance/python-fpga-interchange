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
from fpga_interchange.converters import BaseReaderWriter, to_writer, from_reader


class YamlWriter(BaseReaderWriter):
    def __init__(self, struct_reader, parent):
        super().__init__()
        self.out = {}
        self.struct_reader = struct_reader
        self.parent = parent

    def dereference_value(self, annotation_type, value, root_writer,
                          parent_writer):
        if annotation_type.type == 'root':
            return root_writer.out[annotation_type.field][value]
        elif annotation_type.type == 'rootValue':
            return root_writer.get_field_value(annotation_type.field, value)
        else:
            assert annotation_type.type == 'parent'
            return self.get_parent(
                annotation_type.depth).out[annotation_type.field][value]

    def set_value(self, key, value_which, value):
        self.out[key] = value

    def set_value_inner_key(self, key, inner_key, value_which, value):
        self.out.update({key: {inner_key: value}})

    def make_list(self):
        return []

    def append_to_list(self, l, value_which, value):
        l.append(value)

    def output(self):
        return self.out


class YamlIndexCache():
    def __init__(self, data):
        self.data = data
        self.caches = {}

    def get_index(self, field, value):
        if field not in self.caches:
            self.caches[field] = {}
            for idx, obj in enumerate(self.data[field]):
                self.caches[field][id(obj)] = idx

        return self.caches[field][id(value)]


class YamlReader(BaseReaderWriter):
    def __init__(self, message, data, parent):
        super().__init__()
        self.message = message
        self.data = data
        self.objects = {}
        self.index_cache = YamlIndexCache(self.data)
        self.parent = parent

    def get_index(self, field, value):
        return self.index_cache.get_index(field, value)

    def read_scalar(self, field_which, field_data):
        return field_data

    def reference_value(self, annotation_type, value, root_reader,
                        parent_reader):
        if annotation_type.type == 'root':
            return root_reader.get_index(annotation_type.field, value)
        elif annotation_type.type == 'rootValue':
            return root_reader.objects[annotation_type.field].get_index(value)
        else:
            assert annotation_type.type == 'parent'
            return self.get_parent(annotation_type.depth).get_index(
                annotation_type.field, value)

    def keys(self):
        return self.data.keys()

    def get_field_keys(self, key):
        return self.data[key].keys()

    def get_inner_field(self, key, inner_key):
        return self.data[key][inner_key]

    def get_field(self, key):
        return self.data[key]


def to_yaml(struct_reader):
    return to_writer(struct_reader, YamlWriter)


def from_yaml(message, data):
    from_reader(message, data, YamlReader)
