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

import os
import unittest

from fpga_interchange.convert import read_format, get_schema


class TestConstraintsRoundTrip(unittest.TestCase):
    def test_parse_series7_constraints(self):
        schema = get_schema(os.environ['INTERCHANGE_SCHEMA_PATH'], 'device',
                            'Device.Constraints')
        path = os.path.join('test_data', 'series7_constraints.yaml')
        with open(path, 'rb') as f:
            _ = read_format(schema, 'yaml', f)

    def test_parse_ecp5_constraints(self):
        schema = get_schema(os.environ['INTERCHANGE_SCHEMA_PATH'], 'device',
                            'Device.Constraints')
        path = os.path.join('test_data', 'ecp5_constraints.yaml')
        with open(path, 'rb') as f:
            _ = read_format(schema, 'yaml', f)
