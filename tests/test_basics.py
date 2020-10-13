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
import tempfile

from fpga_interchange.logical_netlist import Library, Cell, Direction, CellInstance, LogicalNetlist
from fpga_interchange.interchange_capnp import Interchange, write_capnp_file


class TestRoundTrip(unittest.TestCase):
    def test_logical_netlist(self):
        hdi_primitives = Library('hdi_primitives')

        cell = Cell('FDRE')
        cell.add_port('D', Direction.Input)
        cell.add_port('C', Direction.Input)
        cell.add_port('CE', Direction.Input)
        cell.add_port('R', Direction.Input)
        cell.add_port('Q', Direction.Output)
        hdi_primitives.add_cell(cell)

        cell = Cell('IBUF')
        cell.add_port('I', Direction.Input)
        cell.add_port('O', Direction.Output)
        hdi_primitives.add_cell(cell)

        cell = Cell('OBUF')
        cell.add_port('I', Direction.Input)
        cell.add_port('O', Direction.Output)
        hdi_primitives.add_cell(cell)

        cell = Cell('BUFG')
        cell.add_port('I', Direction.Input)
        cell.add_port('O', Direction.Output)
        hdi_primitives.add_cell(cell)

        cell = Cell('VCC')
        cell.add_port('P', Direction.Output)
        hdi_primitives.add_cell(cell)

        cell = Cell('GND')
        cell.add_port('G', Direction.Output)
        hdi_primitives.add_cell(cell)

        top = Cell('top')
        top.add_port('i', Direction.Input)
        top.add_port('clk', Direction.Input)
        top.add_port('o', Direction.Output)

        top.add_cell_instance('ibuf', 'IBUF')
        top.add_cell_instance('obuf', 'OBUF')
        top.add_cell_instance('clk_buf', 'BUFG')
        top.add_cell_instance('ff', 'FDRE')
        top.add_cell_instance('VCC', 'VCC')
        top.add_cell_instance('GND', 'GND')

        top.add_net('i')
        top.connect_net_to_cell_port('i', 'i')
        top.connect_net_to_instance('i', 'ibuf', 'I')

        top.add_net('i_buf')
        top.connect_net_to_instance('i_buf', 'ibuf', 'O')
        top.connect_net_to_instance('i_buf', 'ff', 'D')

        top.add_net('o_buf')
        top.connect_net_to_instance('o_buf', 'ff', 'Q')
        top.connect_net_to_instance('o_buf', 'obuf', 'I')

        top.add_net('o')
        top.connect_net_to_instance('o', 'obuf', 'O')
        top.connect_net_to_cell_port('o', 'o')

        top.add_net('clk')
        top.connect_net_to_cell_port('clk', 'clk')
        top.connect_net_to_instance('clk', 'clk_buf', 'I')

        top.add_net('clk_buf')
        top.connect_net_to_instance('clk_buf', 'clk_buf', 'O')
        top.connect_net_to_instance('clk_buf', 'ff', 'C')

        top.add_net('GLOBAL_LOGIC1')
        top.connect_net_to_instance('GLOBAL_LOGIC1', 'VCC', 'P')
        top.connect_net_to_instance('GLOBAL_LOGIC1', 'ff', 'CE')

        top.add_net('GLOBAL_LOGIC0')
        top.connect_net_to_instance('GLOBAL_LOGIC0', 'GND', 'G')
        top.connect_net_to_instance('GLOBAL_LOGIC0', 'ff', 'R')

        work = Library('work')
        work.add_cell(top)

        logical_netlist = LogicalNetlist(
            name='top',
            top_instance_name='top',
            top_instance=CellInstance(
                cell_name='top',
                view='netlist',
                property_map={},
            ),
            property_map={},
            libraries={
                'work': work,
                'hdi_primitives': hdi_primitives,
            })

        interchange = Interchange(
            schema_directory=os.environ['INTERCHANGE_SCHEMA_PATH'])

        with tempfile.NamedTemporaryFile('w+b') as f:
            netlist_capnp = logical_netlist.convert_to_capnp(interchange)
            write_capnp_file(netlist_capnp, f)
            f.seek(0)
            read_logical_netlist = LogicalNetlist.read_from_capnp(
                f, interchange)

        self.assertEqual(read_logical_netlist.name, logical_netlist.name)
        self.assertEqual(read_logical_netlist.top_instance,
                         logical_netlist.top_instance)

        self.assertEqual(read_logical_netlist.libraries.keys(),
                         logical_netlist.libraries.keys())
        for library_name, library in logical_netlist.libraries.items():
            read_library = read_logical_netlist.libraries[library_name]
            self.assertEqual(library.cells.keys(), read_library.cells.keys())
            for cell_name, cell in library.cells.items():
                read_cell = read_library.cells[cell_name]

                self.assertEqual(cell.name, read_cell.name)
                self.assertEqual(cell.property_map, read_cell.property_map)
                self.assertEqual(cell.view, read_cell.view)
                self.assertEqual(cell.nets.keys(), read_cell.nets.keys())
                self.assertEqual(cell.ports.keys(), read_cell.ports.keys())
                self.assertEqual(cell.cell_instances.keys(),
                                 read_cell.cell_instances.keys())
