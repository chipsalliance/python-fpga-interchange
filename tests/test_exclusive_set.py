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

import unittest

from fpga_interchange.constraints.sat import ExclusiveStateGroup, Solver
from pysat.solvers import Solver as SatSolver

DEBUG = False


class TestExclusiveSet(unittest.TestCase):
    def test_two_state_set(self):
        state_group = ExclusiveStateGroup('TEST', 'default')

        state_group.add_state('default')
        state_group.add_state('state1')

        solver = Solver()
        solver.add_state_group(state_group)

        clauses = solver.prepare_for_sat()

        for state in state_group.states:
            with SatSolver() as sat:
                for clause in clauses:
                    sat.add_clause(clause)

                variable_name = state_group.assert_state(state).variable_name()
                assumptions = [solver.get_variable(variable_name)]
                self.assertTrue(sat.solve(assumptions=assumptions))

                model = sat.get_model()
                state_groups_vars, other_vars = solver.decode_solution_model(
                    model)
                self.assertEqual(other_vars, set())
                self.assertEqual(state_groups_vars, {'TEST': state})

    def test_four_state_set(self):
        state_group = ExclusiveStateGroup('TEST', 'default')

        state_group.add_state('default')
        state_group.add_state('state1')
        state_group.add_state('state2')
        state_group.add_state('state3')

        solver = Solver()
        solver.add_state_group(state_group)

        clauses = solver.prepare_for_sat()

        if DEBUG:
            for variable_name, variable_idx in sorted(
                    solver.variable_name_to_index.items(), key=lambda x: x[1]):
                print('{: 10d} - {}'.format(variable_idx, variable_name))

            print('Clauses:')
            for clause in clauses:
                print(clause)

        for state in state_group.states:
            with SatSolver() as sat:
                for clause in clauses:
                    sat.add_clause(clause)

                variable_name = state_group.assert_state(state).variable_name()
                assumptions = [solver.get_variable(variable_name)]

                if DEBUG:
                    print('Assumptions:')
                    print(assumptions)

                result = sat.solve(assumptions=assumptions)
                if not result:
                    if DEBUG:
                        print('Core:')
                        print(sat.get_core())
                    self.assertTrue(result)

                model = sat.get_model()
                state_groups_vars, other_vars = solver.decode_solution_model(
                    model)
                self.assertEqual(other_vars, set())
                self.assertEqual(state_groups_vars, {'TEST': state})


if __name__ == '__main__':
    unittest.main()
