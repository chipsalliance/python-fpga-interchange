#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2021  The F4PGA Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC


class LutCell():
    def __init__(self):
        self.name = ''
        self.pins = []


class LutBel():
    def __init__(self):
        self.name = ''
        self.pins = []
        self.low_bit = 0
        self.high_bit = 0
        self.out_pin = ''


class LutElement():
    def __init__(self):
        self.width = 0
        self.lut_bels = []
