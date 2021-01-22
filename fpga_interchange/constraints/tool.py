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

import argparse
import pprint
from pysat.solvers import Solver
import sys

from fpga_interchange.interchange_capnp import Interchange
from fpga_interchange.constraints.placement_oracle import PlacementOracle
from fpga_interchange.constraints.model import CellInstance, Placement


def make_problem_from_device(device, allowed_sites):
    """ Generate constraint problem from device database. """
    model = device.get_constraints()

    placement_oracle = PlacementOracle()
    placement_oracle.add_sites_from_device(device)

    placements = []
    for tile, site, tile_type, site_type, bel in device.yield_bels():
        if site not in allowed_sites:
            continue

        placements.append(
            Placement(
                tile=tile,
                site=site,
                tile_type=tile_type,
                site_type=site_type,
                bel=bel))

    return model, placement_oracle, placements


def create_constraint_cells_from_netlist(netlist, filtered_out=set()):
    """ Generate cells from logical netlist. """
    cells = []
    for leaf_cell_name, cell_inst in netlist.yield_leaf_cells():
        if cell_inst.cell_name in filtered_out:
            continue

        cells.append(
            CellInstance(
                cell=cell_inst.cell_name, name=leaf_cell_name, ports={}))

    return cells


def main():
    parser = argparse.ArgumentParser(
        description="Run FPGA constraints placement engine.")
    parser.add_argument('--schema_dir', required=True)
    parser.add_argument(
        '--assumptions', help='Comma seperated list of assumptions to hold')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--allowed_sites', required=True)
    parser.add_argument('--filtered_cells')
    parser.add_argument('device')
    parser.add_argument('netlist')

    args = parser.parse_args()

    interchange = Interchange(args.schema_dir)

    with open(args.device, 'rb') as f:
        device = interchange.read_device_resources(f)

    with open(args.netlist, 'rb') as f:
        netlist = interchange.read_logical_netlist(f)

    allowed_sites = set(args.allowed_sites.split(','))
    filtered_cells = set()
    if args.filtered_cells is not None:
        filtered_cells = set(cell for cell in args.filtered_cells.split(','))

    model, placement_oracle, placements = make_problem_from_device(
        device, allowed_sites)
    cells = create_constraint_cells_from_netlist(netlist, filtered_cells)

    solver = model.build_sat(placements, cells, placement_oracle)

    if args.verbose:
        print()
        print("Preparing solver")
        print()
    clauses = solver.prepare_for_sat()

    if args.verbose:
        print()
        print("Variable names ({} total):".format(len(solver.variable_names)))
        print()
        for variable in solver.variable_names:
            print(variable)

        print()
        print("Clauses:")
        print()
        for clause in solver.abstract_clauses:
            print(clause)

    assumptions = []

    if args.assumptions:
        for assumption in args.assumptions.split(','):
            assumptions.append(solver.get_variable(assumption))

    with Solver() as sat:
        for clause in clauses:
            if args.verbose:
                print(clause)
            sat.add_clause(clause)

        if args.verbose:
            print()
            print("Running SAT:")
            print()
            print("Assumptions:")
            print(assumptions)

        solved = sat.solve(assumptions=assumptions)
        if args.verbose:
            print(sat.time())

        if solved:
            model = sat.get_model()
        else:
            core = sat.get_core()

    if solved:
        if args.verbose:
            print()
            print("Raw Solution:")
            print()
            print(model)

        print("Solution:")
        state_groups_vars, other_vars = solver.decode_solution_model(model)
        assert len(other_vars) == 0

        pprint.pprint(state_groups_vars)
    else:
        print("Unsatifiable!")
        if core is not None:
            print("Core:")
            print(core)
            print("Core variables:")
            for core_index in core:
                print(solver.variable_names[core_index])
        sys.exit(1)


if __name__ == "__main__":
    main()
