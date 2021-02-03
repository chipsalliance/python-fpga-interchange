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
from pysat.solvers import Solver

from fpga_interchange.convert import read_format, get_schema
from fpga_interchange.interchange_capnp import Interchange
from fpga_interchange.device_resources import DeviceResources
from fpga_interchange.patch import patch_capnp
from fpga_interchange.compare import compare_capnp
from fpga_interchange.constraints.tool import make_problem_from_device, \
        create_constraint_cells_from_netlist
from example_netlist import example_physical_netlist, example_logical_netlist


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

    def test_patch_series7_constraints(self):
        phys_netlist = example_physical_netlist()

        interchange = Interchange(
            schema_directory=os.environ['INTERCHANGE_SCHEMA_PATH'])

        with open(
                os.path.join(os.environ['DEVICE_RESOURCE_PATH'],
                             phys_netlist.part + '.device'), 'rb') as f:
            dev_message = interchange.read_device_resources_raw(f)

        dev_message = dev_message.as_builder()

        path = os.path.join('test_data', 'series7_constraints.yaml')
        with open(path, 'rb') as f:
            patch_capnp(dev_message, ['constraints'], 'yaml', f)

        schema = get_schema(os.environ['INTERCHANGE_SCHEMA_PATH'], 'device',
                            'Device.Constraints')
        with open(path, 'rb') as f:
            series7 = read_format(schema, 'yaml', f)

        compare_capnp(self, series7, dev_message.constraints)

    def test_simple_placement(self):
        netlist = example_logical_netlist()
        cells = create_constraint_cells_from_netlist(
            netlist, filtered_out={'GND', 'VCC'})

        phys_netlist = example_physical_netlist()

        interchange = Interchange(
            schema_directory=os.environ['INTERCHANGE_SCHEMA_PATH'])

        with open(
                os.path.join(os.environ['DEVICE_RESOURCE_PATH'],
                             phys_netlist.part + '.device'), 'rb') as f:
            dev_message = interchange.read_device_resources_raw(f)

        dev_message = dev_message.as_builder()

        path = os.path.join('test_data', 'series7_constraints.yaml')
        with open(path, 'rb') as f:
            patch_capnp(dev_message, ['constraints'], 'yaml', f)

        device = DeviceResources(dev_message)

        allowed_sites = {
            'IOB_X0Y0',
            'IOB_X0Y1',
            'IOB_X0Y2',
            'SLICE_X0Y0',
            'BUFGCTRL_X0Y0',
        }

        model, placement_oracle, placements = make_problem_from_device(
            device, allowed_sites)

        solver = model.build_sat(placements, cells, placement_oracle)
        clauses = solver.prepare_for_sat()

        with Solver() as sat:
            for clause in clauses:
                sat.add_clause(clause)

            solved = sat.solve()
            self.assertTrue(solved)
