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

import os.path
import unittest
from pysat.solvers import Solver

from example_netlist import example_physical_netlist
from fpga_interchange.interchange_capnp import Interchange
from fpga_interchange.convert import read_format, get_schema
from fpga_interchange.constraints.model import Constraints, CellInstance, Placement
from fpga_interchange.constraints.placement_oracle import PlacementOracle


def create_bram_tile(grid_x, grid_y, bram18_x0, bram18_y0, bram36_x0,
                     bram36_y0):
    """ Create a BRAM_L/R like tile, with 2 RAMB18E1 sites and 1 RAMB36E1 site. """
    tile_name = 'BRAM_X{}Y{}'.format(grid_x, grid_y)
    yield Placement(
        tile=tile_name,
        tile_type='BRAM_L',
        site='RAMB36E1_X{}Y{}'.format(bram36_x0, bram36_y0),
        site_type='RAMB36E1',
        bel='RAMB36E1')

    for dy in range(2):
        yield Placement(
            tile=tile_name,
            tile_type='BRAM_L',
            site='RAMB18E1_X{}Y{}'.format(bram18_x0, bram18_y0 + dy),
            site_type='RAMB18E1',
            bel='RAMB18E1')


def create_placements(number_rows, number_cols):
    """ Create a simple grid of BRAM_L/R like tiles. """
    for grid_x in range(number_rows):
        for grid_y in range(number_cols):
            for placement in create_bram_tile(
                    grid_x=grid_x,
                    grid_y=grid_y,
                    bram18_x0=grid_x,
                    bram18_y0=grid_y * 2,
                    bram36_x0=grid_x,
                    bram36_y0=grid_y,
            ):
                yield placement


def create_cells(number_ramb18, number_ramb36):
    """ Creates some RAMB18E1 and RAMB36E1 cells for placement. """
    for ramb18_idx in range(number_ramb18):
        yield CellInstance(
            cell='RAMB18E1', name='RAMB18_{}'.format(ramb18_idx), ports={})

    for ramb36_idx in range(number_ramb36):
        yield CellInstance(
            cell='RAMB36E1', name='RAMB36_{}'.format(ramb36_idx), ports={})


class TestBramConstraints(unittest.TestCase):
    def setUp(self):
        schema = get_schema(os.environ['INTERCHANGE_SCHEMA_PATH'], 'device',
                            'Device.Constraints')
        path = os.path.join('test_data', 'series7_constraints.yaml')
        with open(path, 'rb') as f:
            constraints = read_format(schema, 'yaml', f)

        self.model = Constraints()
        self.model.read_constraints(constraints)

        interchange = Interchange(
            schema_directory=os.environ['INTERCHANGE_SCHEMA_PATH'])
        phys_netlist = example_physical_netlist()
        with open(
                os.path.join(os.environ['DEVICE_RESOURCE_PATH'],
                             phys_netlist.part + '.device'), 'rb') as f:
            device = interchange.read_device_resources(f)

        self.placement_oracle = PlacementOracle()
        self.placement_oracle.add_sites_from_device(device)

    def assertFits(self, placements, cells):
        """ Assert that the cells fits in the placement locations provided.

        Also checks that the BRAM_MODE tile constraint is obeyed.

        """
        placements = list(placements)
        cells = list(cells)

        # Create some lookups for cells, tiles and grids.
        cell_names = set(cell.name for cell in cells)
        cell_name_to_cell = {}
        for cell in cells:
            assert cell.name not in cell_name_to_cell
            cell_name_to_cell[cell.name] = cell

        sites = {}
        tiles = {}
        sites_to_tile = {}
        for placement in placements:
            tiles[placement.tile] = None
            sites[placement.site] = None
            sites_to_tile[placement.site] = placement.tile

        # Setup the SAT solver
        solver = self.model.build_sat(placements, cells, self.placement_oracle)
        clauses = solver.prepare_for_sat()

        cell_placements = {}

        with Solver() as sat:
            for clause in clauses:
                sat.add_clause(clause)

            # sat.solve returns True if the system of equations has a solution.
            self.assertTrue(sat.solve())
            # model is one example solution
            model = sat.get_model()

            # Convert example solution into state group variables.
            state_groups_vars, other_vars = solver.decode_solution_model(model)
            self.assertEqual(len(other_vars), 0)

            # Convert tile BRAM_MODE state and cell placements into tiles and
            # placements dict.
            for variable, state in state_groups_vars.items():
                if variable.endswith('.BRAM_MODE'):
                    tile = variable[:-(len('BRAM_MODE') + 1)]

                    if tiles[tile] is None:
                        tiles[tile] = state
                    else:
                        assert tiles[tile] == state

                if variable in cell_names:
                    cell_name = variable
                    site, _ = state.split('.')
                    self.assertTrue(site in sites)
                    self.assertTrue(cell_name not in cell_placements)
                    cell_placements[cell_name] = site

        # For each cell placement, ensure that the BRAM mode constraint was
        # followed.
        for cell_name, site in cell_placements.items():
            self.assertTrue(sites[site] is None)
            sites[site] = cell_name

            cell = cell_name_to_cell[cell_name]

            tile = sites_to_tile[site]

            if cell.cell == 'RAMB18E1':
                self.assertEqual(tiles[tile], '2xRAMB18')
            elif cell.cell == 'RAMB36E1':
                self.assertEqual(tiles[tile], 'RAMB36')
            else:
                assert False, cell.cell

    def assertDoesNotFit(self, placements, cells):
        """ Asserts that the cells does not fit in the placements. """
        placements = list(placements)
        cells = list(cells)

        solver = self.model.build_sat(placements, cells, self.placement_oracle)
        clauses = solver.prepare_for_sat()

        with Solver() as sat:
            for clause in clauses:
                sat.add_clause(clause)

            # sat.solve returns False, which means that there is no solution.
            self.assertFalse(sat.solve())

    def test_1_of_each_cell(self):
        self.assertFits(
            placements=create_placements(4, 4),
            cells=create_cells(number_ramb18=1, number_ramb36=0))
        self.assertFits(
            placements=create_placements(4, 4),
            cells=create_cells(number_ramb18=0, number_ramb36=1))
        self.assertFits(
            placements=create_placements(4, 4),
            cells=create_cells(number_ramb18=1, number_ramb36=1))

    def test_perfect_fit(self):
        # In a 4x4 placement, you can fit:
        # - 16 RAMB36
        # - 32 RAMB18
        # - Or trade 1 36 for 2 18's
        self.assertFits(
            placements=create_placements(4, 4),
            cells=create_cells(number_ramb18=32, number_ramb36=0))
        self.assertFits(
            placements=create_placements(4, 4),
            cells=create_cells(number_ramb18=0, number_ramb36=16))
        self.assertFits(
            placements=create_placements(4, 4),
            cells=create_cells(number_ramb18=2, number_ramb36=15))
        self.assertFits(
            placements=create_placements(4, 4),
            cells=create_cells(number_ramb18=4, number_ramb36=14))
        self.assertFits(
            placements=create_placements(4, 4),
            cells=create_cells(number_ramb18=30, number_ramb36=1))

    def test_too_small(self):
        # A 2x2 grid has 8 maximum RAMB18 or 4 maximum RAMB36.
        self.assertFits(
            placements=create_placements(2, 2),
            cells=create_cells(number_ramb18=8, number_ramb36=0))
        self.assertDoesNotFit(
            placements=create_placements(2, 2),
            cells=create_cells(number_ramb18=9, number_ramb36=0))

        self.assertFits(
            placements=create_placements(2, 2),
            cells=create_cells(number_ramb18=0, number_ramb36=4))
        self.assertDoesNotFit(
            placements=create_placements(2, 2),
            cells=create_cells(number_ramb18=0, number_ramb36=5))

        self.assertFits(
            placements=create_placements(2, 2),
            cells=create_cells(number_ramb18=6, number_ramb36=1))
        self.assertDoesNotFit(
            placements=create_placements(2, 2),
            cells=create_cells(number_ramb18=8, number_ramb36=1))

        self.assertFits(
            placements=create_placements(2, 2),
            cells=create_cells(number_ramb18=1, number_ramb36=3))
        self.assertDoesNotFit(
            placements=create_placements(2, 2),
            cells=create_cells(number_ramb18=1, number_ramb36=4))

        self.assertDoesNotFit(
            placements=create_placements(5, 1),
            cells=create_cells(number_ramb18=10, number_ramb36=1))


if __name__ == '__main__':
    unittest.main()
