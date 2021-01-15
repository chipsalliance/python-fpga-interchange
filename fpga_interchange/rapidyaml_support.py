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
from fpga_interchange.converters import BaseReaderWriter, to_writer, from_reader, SCALAR_TYPES
import ryml
from ryml import Tree

CHECK_TREE = True


class YamlReference():
    def __init__(self, ref):
        self.ref = ref


def mkvalue(v):
    if v is True:
        return 'true'
    elif v is False:
        return 'false'
    elif v is None:
        return 'null'
    else:
        return str(v)


def set_key_val_ref(tree, mkstr, keyval_id, key, ref):
    assert isinstance(ref, YamlReference)
    # FIXME: Bug in RapidYaml requires setting the value to also be the ref
    # string.
    tree.to_keyval(keyval_id, mkstr(key), mkstr('*' + ref.ref))
    tree.set_val_ref(keyval_id, ref.ref)


def set_val_ref(tree, mkstr, val_id, ref):
    assert isinstance(ref, YamlReference)
    # FIXME: Bug in RapidYaml requires setting the value to also be the ref
    # string.
    tree.to_val(val_id, mkstr('*' + ref.ref))
    tree.set_val_ref(val_id, ref.ref)


class RapidYamlWriter(BaseReaderWriter):
    def __init__(self, struct_reader, parent):
        super().__init__()

        if parent is None:
            self.tree = Tree()
            self.tree.reserve(16)
            self.id = self.tree.root_id()
            self.strings = []
            self.tree.to_map(self.id)
            self.nursery_id = self.tree.append_child(self.id)
            self.tree.to_seq(self.nursery_id)
        else:
            self.tree = parent.tree
            self.nursery_id = parent.nursery_id
            self.id = self.tree.append_child(self.nursery_id)
            self.strings = parent.strings
            self.tree.to_map(self.id)

        self.field_ids = {}
        self.list_ids = {}
        self.struct_reader = struct_reader
        self.parent = parent
        self.ref_index = 1

    def mkstr(self, s):
        self.strings.append(s)
        return self.strings[-1]

    def make_reference(self, ref_id):
        if self.tree.is_anchor(ref_id):
            return YamlReference(
                self.mkstr(
                    bytes(self.tree.val_anchor(ref_id)).decode('utf-8')))
        else:
            ref = self.mkstr('id{:03d}'.format(self.ref_index))
            self.ref_index += 1

            self.tree.set_val_anchor(ref_id, ref)
            return YamlReference(ref)

    def get_list_id(self, field, index):
        field_id = self.field_ids[field]
        if field_id not in self.list_ids:
            l = []
            for value_id in ryml.children(self.tree, field_id):
                l.append(value_id)
            self.list_ids[field_id] = l

        return self.list_ids[field_id][index]

    def dereference_value(self, annotation_type, value, root_writer,
                          parent_writer):
        if annotation_type.type == 'root':
            ref_id = root_writer.get_list_id(annotation_type.field, value)
            return root_writer.make_reference(ref_id)

        elif annotation_type.type == 'rootValue':
            return root_writer.get_field_value(annotation_type.field, value)
        else:
            assert annotation_type.type == 'parent'
            parent = self.get_parent(annotation_type.depth)
            ref_id = parent.get_list_id(annotation_type.field, value)

            assert ref_id != ryml.NONE
            assert not self.tree.has_key(ref_id)

            return root_writer.make_reference(ref_id)

    def set_value(self, key, value_which, value):
        if isinstance(value, YamlReference):
            keyval_id = self.tree.append_child(self.id)
            set_key_val_ref(self.tree, self.mkstr, keyval_id, key, value)
            return

        if value_which in SCALAR_TYPES:
            keyval_id = self.tree.append_child(self.id)
            self.field_ids[key] = keyval_id
            self.tree.to_keyval(keyval_id, self.mkstr(key),
                                self.mkstr(mkvalue(value)))
        elif value_which == 'list':
            list_id = value
            assert self.tree.parent(list_id) == self.id
            self.field_ids[key] = list_id
            self.tree._set_key(list_id, self.mkstr(key))
        elif value_which == 'void':
            keyval_id = self.tree.append_child(self.id)
            self.field_ids[key] = keyval_id
            self.tree.to_keyval(keyval_id, self.mkstr(key), self.mkstr('null'))
        elif value_which == 'enum':
            keyval_id = self.tree.append_child(self.id)
            self.field_ids[key] = keyval_id
            self.tree.to_keyval(keyval_id, self.mkstr(key), self.mkstr(value))
        elif value_which == 'struct':
            assert value != ryml.NONE
            assert self.tree.parent(value) == self.nursery_id
            assert self.tree.is_map(value)
            self.tree.move(value, self.id, self.tree.last_child(self.id))
            self.tree._set_key(value, self.mkstr(key))
            self.field_ids[key] = value
        else:
            assert False, value_which

    def set_value_inner_key(self, key, inner_key, value_which, value):
        outer_id = self.tree.append_child(self.id)
        self.tree.to_map(outer_id, self.mkstr(key))

        if isinstance(value, YamlReference):
            keyval_id = self.tree.append_child(outer_id)
            set_key_val_ref(self.tree, self.mkstr, keyval_id, inner_key, value)
            return

        if value_which in SCALAR_TYPES:
            keyval_id = self.tree.append_child(outer_id)
            self.tree.to_keyval(keyval_id, self.mkstr(inner_key),
                                self.mkstr(mkvalue(value)))
        elif value_which == 'list':
            list_id = value
            assert list_id != ryml.NONE
            assert self.tree.parent(list_id) == self.id
            self.tree.move(list_id, outer_id, ryml.NONE)
            self.tree._set_key(list_id, self.mkstr(inner_key))

            assert self.tree.parent(list_id) == outer_id
            assert self.tree.num_children(outer_id) == 1
            assert self.tree.first_child(outer_id) == list_id

        elif value_which == 'void':
            keyval_id = self.tree.append_child(outer_id)
            self.tree.to_keyval(keyval_id, self.mkstr(inner_key),
                                self.mkstr('null'))
        elif value_which == 'enum':
            keyval_id = self.tree.append_child(outer_id)
            self.tree.to_keyval(keyval_id, self.mkstr(inner_key),
                                self.mkstr(value))
        elif value_which == 'struct':
            assert value != ryml.NONE
            assert self.tree.parent(value) == self.nursery_id
            assert self.tree.is_map(value)

            self.tree.move(value, outer_id, ryml.NONE)
            self.tree._set_key(value, self.mkstr(inner_key))

            assert self.tree.parent(value) == outer_id
            assert self.tree.num_children(outer_id) == 1
            assert self.tree.first_child(outer_id) == value
        else:
            assert False, value_which

    def make_list(self):
        list_id = self.tree.append_child(self.id)
        self.tree.to_seq(list_id)
        return list_id

    def append_to_list(self, list_id, value_which, value):
        if isinstance(value, YamlReference):
            val_id = self.tree.append_child(list_id)
            set_val_ref(self.tree, self.mkstr, val_id, value)
            return

        if value_which == 'struct':
            assert self.tree.parent(value) == self.nursery_id
            assert self.tree.is_map(value)

            self.tree.move(value, list_id, self.tree.last_child(list_id))

            assert self.tree.parent(value) == list_id
        else:
            assert value_which in SCALAR_TYPES
            val_id = self.tree.append_child(list_id)
            self.tree.to_val(val_id, self.mkstr(mkvalue(value)))

    def output(self):
        if self.parent is None:
            if CHECK_TREE:
                seen_nodes = set()
                for node, il in ryml.walk(self.tree):
                    assert node not in seen_nodes, (node, il)
                    seen_nodes.add(node)

            assert self.tree.num_children(self.nursery_id) == 0
            self.tree.remove(self.nursery_id)

            return self.strings, self.tree
        else:
            return self.id


def handle_value(s):
    if s is None:
        return s
    else:
        return bytes(s).decode('utf-8')


def get_value(tree, field_id):
    if tree.is_val_ref(field_id):
        return YamlReference(bytes(tree.val_ref(field_id)).decode('utf-8'))

    if tree.is_map(field_id):
        return field_id
    elif tree.is_seq(field_id):
        value_id = tree.first_child(field_id)
        if value_id == ryml.NONE:
            return []

        assert not tree.is_seq(value_id)
        if tree.is_map(value_id):
            return list(ryml.children(tree, field_id))
        else:
            out = []
            for value_id in ryml.children(tree, field_id):
                if tree.is_val_ref(value_id):
                    out.append(
                        YamlReference(
                            bytes(tree.val_ref(value_id)).decode('utf-8')))
                else:
                    s = handle_value(tree.val(value_id))
                    out.append(s)
            return out
    else:
        s = handle_value(tree.val(field_id))
        return s


class RapidYamlReader(BaseReaderWriter):
    def __init__(self, message, data, parent):
        super().__init__()

        self.parent = parent
        if self.parent is None:
            self.tree = data
            self.id = self.tree.root_id()
        else:
            self.tree = parent.tree
            self.id = data

        self.field_ids = {}
        self.field_refs = {}
        self.objects = {}

        self.message = message

    def _init_fields(self):
        if len(self.field_ids) > 0:
            return

        assert self.tree.is_map(self.id)

        for field_id in ryml.children(self.tree, self.id):
            field_key = bytes(self.tree.key(field_id)).decode('utf-8')

            assert field_key not in self.field_ids
            self.field_ids[field_key] = field_id

    def find_ref_index(self, field, target_ref):
        self._init_fields()

        if field not in self.field_refs:
            field_id = self.field_ids[field]
            self.field_refs[field] = {}
            for idx, value_id in enumerate(ryml.children(self.tree, field_id)):
                if self.tree.is_anchor(value_id):
                    ref = bytes(self.tree.val_anchor(value_id)).decode('utf-8')
                    assert ref not in self.field_refs[field]
                    self.field_refs[field][ref] = idx

        return self.field_refs[field][target_ref]

    def read_scalar(self, field_which, field_data):
        if field_which == 'text':
            return field_data
        elif field_which == 'bool':
            if field_data == True:
                return True
            elif field_data == False:
                return False
            elif field_data == 'true':
                return True
            elif field_data == 'false':
                return False
            else:
                assert False, field_data
        elif field_which == 'float32' and field_which == 'float64':
            return float(field_data)
        else:
            return int(field_data)

    def reference_value(self, annotation_type, value, root_reader,
                        parent_reader):
        if annotation_type.type == 'root':
            assert isinstance(value, YamlReference)
            return root_reader.find_ref_index(annotation_type.field, value.ref)
        elif annotation_type.type == 'rootValue':
            return root_reader.objects[annotation_type.field].get_index(value)
        else:
            assert annotation_type.type == 'parent'
            assert isinstance(value, YamlReference)
            return self.get_parent(annotation_type.depth).find_ref_index(
                annotation_type.field, value.ref)

    def keys(self):
        self._init_fields()
        return self.field_ids.keys()

    def get_field_keys(self, key):
        self._init_fields()
        outer_id = self.field_ids[key]
        assert self.tree.num_children(outer_id) == 1
        field_id = self.tree.first_child(outer_id)
        return {bytes(self.tree.key(field_id)).decode('utf-8'): None}.keys()

    def get_inner_field(self, key, inner_key):
        self._init_fields()
        outer_id = self.field_ids[key]
        assert self.tree.num_children(outer_id) == 1
        field_id = self.tree.first_child(outer_id)

        return get_value(self.tree, field_id)

    def get_field(self, key):
        self._init_fields()
        field_id = self.field_ids[key]

        return get_value(self.tree, field_id)


def to_rapidyaml(struct_reader):
    return to_writer(struct_reader, RapidYamlWriter)


def from_rapidyaml(message, data):
    from_reader(message, data, RapidYamlReader)
