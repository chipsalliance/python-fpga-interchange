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


class PortType(Enum):
    PORT_IN = 0
    PORT_OUT = 1
    PORT_INOUT = 2


class BbaWriter():
    def __init__(self, f, const_ids):
        self.f = f
        self.const_ids = const_ids

        self.labels = set()
        self.refs = set()

    def println(self, s):
        print(s, file=self.f)

    def u8(self, value):
        print('u8 {}'.format(value), file=self.f)

    def u16(self, value):
        print('u16 {}'.format(value), file=self.f)

    def u32(self, value):
        print('u32 {}'.format(value), file=self.f)

    def label(self, label, label_type):
        assert label not in self.labels, label
        self.labels.add(label)
        print('label {} {}'.format(label, label_type), file=self.f)

    def ref(self, ref, comment=None):
        self.refs.add(ref)
        if comment is None:
            print('ref {}'.format(ref), file=self.f)
        else:
            print('ref {} {}'.format(ref, comment), file=self.f)

    def str(self, s, comment=None):
        if comment is None:
            print('str |{}|'.format(s), file=self.f)
        else:
            print('str |{}| {}'.format(s, comment), file=self.f)

    def str_id(self, s):
        if s == ('', ):
            index = self.const_ids.get_index('')
        else:
            index = self.const_ids.get_index(s)

            # Pretty weird to see an empty string here, fail and make sure that
            # this was the intention.
            assert index > 0, s

        self.u32(index)

    def pre(self, s):
        print("pre {}".format(s), file=self.f)

    def post(self, s):
        print("post {}".format(s), file=self.f)

    def push(self, name):
        print("push {}".format(name), file=self.f)

    def pop(self):
        print("pop", file=self.f)

    def check_labels(self):
        refs_and_labels = self.refs & self.labels
        assert len(refs_and_labels) == len(self.refs)
        assert len(refs_and_labels) == len(self.labels)
