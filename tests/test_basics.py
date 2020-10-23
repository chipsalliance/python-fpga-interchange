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
import pprint
import tempfile

from fpga_interchange.interchange_capnp import Interchange, write_capnp_file, \
        CompressionFormat
from fpga_interchange.logical_netlist import LogicalNetlist
from fpga_interchange.physical_netlist import PhysicalNetlist
from example_netlist import example_logical_netlist, example_physical_netlist


class TestRoundTrip(unittest.TestCase):
    def test_logical_netlist(self):
        logical_netlist = example_logical_netlist()

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

    def test_physical_netlist(self):
        phys_netlist = example_physical_netlist()

        interchange = Interchange(
            schema_directory=os.environ['INTERCHANGE_SCHEMA_PATH'])

        with tempfile.NamedTemporaryFile('w+b') as f:
            netlist_capnp = phys_netlist.convert_to_capnp(interchange)
            write_capnp_file(netlist_capnp, f)
            f.seek(0)
            read_phys_netlist = PhysicalNetlist.read_from_capnp(f, interchange)

        self.assertEqual(
            len(phys_netlist.placements), len(read_phys_netlist.placements))

    def test_check_routing_tree_and_stitch_segments(self):
        phys_netlist = example_physical_netlist()

        interchange = Interchange(
            schema_directory=os.environ['INTERCHANGE_SCHEMA_PATH'])

        with open(
                os.path.join(os.environ['DEVICE_RESOURCE_PATH'],
                             phys_netlist.part + '.device'), 'rb') as f:
            device_resources = interchange.read_device_resources(f)

        phys_netlist.check_physical_nets(device_resources)
        before_stitch = phys_netlist.get_normalized_tuple_tree(
            device_resources)
        phys_netlist.stitch_physical_nets(device_resources)
        after_stitch = phys_netlist.get_normalized_tuple_tree(device_resources)
        phys_netlist.stitch_physical_nets(device_resources, flatten=True)
        after_stitch_from_flat = phys_netlist.get_normalized_tuple_tree(
            device_resources)

        self.assertEqual(len(before_stitch), len(after_stitch))
        self.assertEqual(len(before_stitch), len(after_stitch_from_flat))

        bad_nets = set()
        for net in before_stitch:
            if before_stitch[net] != after_stitch[net]:
                bad_nets.add(net)
                print(net)
                pprint.pprint(before_stitch[net])
                pprint.pprint(after_stitch[net])

            if before_stitch[net] != after_stitch_from_flat[net]:
                bad_nets.add(net)
                print(net)
                pprint.pprint(before_stitch[net])
                pprint.pprint(after_stitch_from_flat[net])

        self.assertEqual(set(), bad_nets)

    def test_capnp_modes(self):
        logical_netlist = example_logical_netlist()
        interchange = Interchange(
            schema_directory=os.environ['INTERCHANGE_SCHEMA_PATH'])

        for compression_format in [
                CompressionFormat.UNCOMPRESSED, CompressionFormat.GZIP
        ]:
            for packed in [True, False]:
                with tempfile.NamedTemporaryFile('w+b') as f:
                    netlist_capnp = logical_netlist.convert_to_capnp(
                        interchange)
                    write_capnp_file(
                        netlist_capnp,
                        f,
                        compression_format=compression_format,
                        is_packed=packed)
                    f.seek(0)
                    _ = LogicalNetlist.read_from_capnp(
                        f,
                        interchange,
                        compression_format=compression_format,
                        is_packed=packed)
