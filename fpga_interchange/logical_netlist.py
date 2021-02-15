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

import enum
from collections import namedtuple


# Declares a port on a cell, which is bit or a bus.
#
# If the port is a bit, then bus should be None.
# If the port is a bus, then bus should be a Bus object.
#
# direction should be the Direction object.
#
# property_map should be a dict with str keys, and the values can be str,
# int or bool.
class Port(namedtuple('Port', 'direction property_map bus')):
    def encode_index(self, index):
        """ Encode slice index into bus index.

        A bus defined as [3:0] has a width of 4.  The bus index is the
        distance from the start (e.g. 3) to the end (e.g. 0).

        So ex[3] is bus index 0, ex[2] is bus index 1, etc.

        A bus defined as [0:3] has a width of 4 too, However ex[3] is now bus
        index 3, etc.

        """
        assert self.bus is not None

        if self.bus.start <= self.bus.end:
            assert index >= self.bus.start
            assert index <= self.bus.end
            return index - self.bus.start
        else:
            assert index >= self.bus.end
            assert index <= self.bus.start
            return self.bus.start - index


# Bus range for a port.
#
# start and end should be int.
Bus = namedtuple('Bus', 'start end')

# Port instance either a part of a Net that connects to the Cell port or a
# CellInstance port.
#
# name should be a str with the name of the port.
# If the port is bussed, idx should be the index with the bus, otherwise idx
# should be None.
#
# If the port connects the Cell port, instance_name should be None, otherwise
# instance_name should be the name of the CellInstance this port connects too.
PortInstance = namedtuple('PortInstance', 'name instance_name idx')

# A cell net that connects a driver to one or more sink ports.
#
# name should be a Cell unique net idenfiier.
#
# ports should be a list, where the first entry is either None for an undriven
# net, or the net driver.  Each entry should be a PortInstance object.
#
# property_map should be a dict with str keys, and the values can be str,
# int or bool.
Net = namedtuple('Net', 'name property_map ports')

# A instance of a Cell within the current cell.  Must have a unique name
# within the cell.
#
# property_map should be a dict with str keys, and the values can be str,
# int or bool.
#
# view should be a str and is a deprecate field.
# TODO: Remove view field.
CellInstance = namedtuple('CellInstance', 'property_map view cell_name')


# Direction of a Cell port
class Direction(enum.Enum):
    Input = 0
    Output = 1
    Inout = 2


class Cell():
    """ Utility class for creating a Cell within a logical netlist.

    A Cell consists of:
     - One or more ports (e.g. connections to a high level of the netlist).
     - Zero or more cell instances.  Cell instances are instances of a Cell
       found in a library.  A cell instance definition is found by its name.
       For example "LUT6" or "BUFG" are cell definitions.
     - Zero of more cell nets.  Cell nets connect ports.  The ports can be
       from this cell or ports from cell instances within the cell.

    """

    def __init__(self, name, property_map={}):
        """ Create a new cell

        name (str) - Name of the Cell within the library.
        property_map (dict) - property_map should be a dict with str keys,
                              and the values can be str,  int or bool.

        """
        self.name = name
        self.property_map = property_map
        self.view = "netlist"

        self.nets = {}
        self.ports = {}
        self.cell_instances = {}

        self.cell_pin_net_lookup = {}

    def is_leaf(self):
        return len(self.cell_instances) == 0

    def add_port(self, name, direction, property_map={}):
        """ Add bit port to this cell

        name (str) - Name of the port
        direction (Direction) - Direction of the port.
        property_map (dict) - property_map should be a dict with str keys,
                              and the values can be str,  int or bool.

        """
        assert name not in self.ports

        self.ports[name] = Port(
            direction=direction, property_map=property_map, bus=None)

    def add_bus_port(self, name, direction, start, end, property_map={}):
        """ Add a bussed port to this cell

        name (str) - Name of the port
        direction (Direction) - Direction of the port.
        start (int) - LSB of the port.
        end (int) - MSB of the port.
        property_map (dict) - property_map should be a dict with str keys,
                              and the values can be str,  int or bool.

        """
        assert name not in self.ports
        self.ports[name] = Port(
            direction=direction,
            property_map=property_map,
            bus=Bus(start=start, end=end))

    def add_cell_instance(self, name, cell_name, property_map={}):
        """ Add a cell instance to this cell

        name (str) - Name of Cell instance within this Cell.
        cell_name (str) - Name of library Cell that this instance represents.
        property_map (dict) - property_map should be a dict with str keys,
                              and the values can be str,  int or bool.

        """
        assert name not in self.cell_instances, name
        self.cell_instances[name] = CellInstance(
            property_map=property_map, view="netlist", cell_name=cell_name)

    def add_net(self, name, property_map={}):
        """ Create a new name with the specified name

        name (str) - Name of net within this Cell.
        property_map (dict) - property_map should be a dict with str keys,
                              and the values can be str,  int or bool.

        """
        assert name not in self.nets
        self.nets[name] = Net(name=name, property_map=property_map, ports=[])

    def connect_net_to_instance(self, net_name, instance_name, port, idx=None):
        """ Connect an existing net to an existing instance within the cell.

        net_name (str) - Name of net that has been added with add_net.
        instance_name (str) - Name of cell instance that has been added with
                              add_cell_instance.
        port (str) - Name of port on cell instance.
        idx (int) - Should be None for bit ports or the bus index for bussed
                    port.

        """
        assert instance_name in self.cell_instances
        port_name = port
        port = PortInstance(
            name=port_name, instance_name=instance_name, idx=idx)
        self.nets[net_name].ports.append(port)

        if idx is None:
            cell_pin = port_name
        else:
            cell_pin = '{}[{}]'.format(port_name, idx)

        key = instance_name, cell_pin
        assert key not in self.cell_pin_net_lookup

        self.cell_pin_net_lookup[key] = net_name

    def get_net_name(self, instance_name, cell_pin):
        """ Get the net name for an instance name and cell pin that was added
            via connect_net_to_instance.
        """
        assert instance_name in self.cell_instances, (instance_name, cell_pin)
        return self.cell_pin_net_lookup.get((instance_name, cell_pin), None)

    def connect_net_to_cell_port(self, net_name, port, idx=None):
        """ Connect an existing net to a port on the cell.

        net_name (str) - Name of net that has been added with add_net.
        port (str) - Name of port on this Cell added with add_port or
                     add_bus_port.
        idx (int) - Should be None for bit ports or the bus index for bussed
                    port.

        """
        assert port in self.ports
        port = PortInstance(name=port, idx=idx, instance_name=None)
        self.nets[net_name].ports.append(port)


def invert_direction(direction):
    """ Inverts direction of Direction enum. """
    if direction == Direction.Input:
        return Direction.Output
    elif direction == Direction.Output:
        return Direction.Input
    else:
        assert direction == Direction.Inout
        return Direction.Inout


class Library():
    """ Library of cells. """

    def __init__(self, name):
        self.name = name
        self.cells = {}

    def add_cell(self, cell):
        assert cell.name not in self.cells, cell.name
        self.cells[cell.name] = cell


def yield_leaf_cells(master_cell_list, inst_name, cell_inst):
    cell = master_cell_list[cell_inst.cell_name]

    if cell.is_leaf():
        yield inst_name, cell_inst
    else:
        for inst_name, cell_inst in cell.cell_instances.items():
            for leaf_cell in yield_leaf_cells(master_cell_list, inst_name,
                                              cell_inst):
                yield leaf_cell


class LogicalNetlist(
        namedtuple(
            'LogicalNetlist',
            'name property_map top_instance_name top_instance libraries')):
    @staticmethod
    def read_from_capnp(f, interchange, *args, **kwargs):
        """ Reads a capnp logical netlist into LogicalNetlist object.

        f (file-like)
            File to be read

        interchange (interchange_capnp.Interchange)
            Interchange object holding capnp schema's for the FPGA interchange
            format.

        compression_format (interchange_capnp.CompressionFormat)
            What compression format to use.  Default is
            interchange_capnp.DEFAULT_COMPRESSION_TYPE

        is_packed (bool)
            Whether capnp is packed or not.  Default is
            interchange_capnp.IS_PACKED.

        Returns LogicalNetlist created from input file.

        """
        return interchange.read_logical_netlist(f, *args, **kwargs)

    def convert_to_capnp(self, interchange):
        """ Convert LogicalNetlist object into capnp object.

        Use interchange_capnp.write_capnp_file to write to disk or other
        storage.

        interchange (interchange_capnp.Interchange)
            Interchange object holding capnp schema's for the FPGA interchange
            format.

        """
        return interchange.output_logical_netlist(
            name=self.name,
            libraries=self.libraries,
            top_instance=self.top_instance,
            top_instance_name=self.top_instance_name,
            property_map=self.property_map)

    def get_master_cell_list(self):
        master_cell_list = {}

        for lib in self.libraries.values():
            for cell in lib.cells.values():
                assert cell.name not in master_cell_list
                master_cell_list[cell.name] = cell

        return master_cell_list

    def yield_leaf_cells(self):
        master_cell_list = self.get_master_cell_list()

        for leaf_cell in yield_leaf_cells(
                master_cell_list, self.top_instance_name, self.top_instance):
            yield leaf_cell


def check_logical_netlist(libraries):
    """ Check that a logical netlist is consistent.

    The following things are checked:
     - All cell instances have a paired cell.
     - All cells have a unique cell definition.
     - All port connections on nets match the paired cell model.
     - Nets without Inout ports have only 1 driver.

    Returns a set of Cell names.

    """
    master_cell_list = {}

    for lib in libraries.values():
        for cell in lib.cells.values():
            assert cell.name not in master_cell_list
            master_cell_list[cell.name] = cell

    for cell in master_cell_list.values():
        for inst in cell.cell_instances.values():
            assert inst.cell_name in master_cell_list, inst.cell_name

        for netname, net in cell.nets.items():
            port_directions = {
                Direction.Input: 0,
                Direction.Output: 0,
                Direction.Inout: 0,
            }

            for port in net.ports:
                if port.instance_name is not None:
                    # This port connects to a cell instance, go find the
                    # master cell and port.
                    instance_cell_name = cell.cell_instances[
                        port.instance_name].cell_name
                    instance_cell = master_cell_list[instance_cell_name]
                    assert port.name in instance_cell.ports, (
                        instance_cell_name, )
                    instance_port = instance_cell.ports[port.name]

                    net_direction = invert_direction(instance_port.direction)
                else:
                    instance_port = cell.ports[port.name]

                    net_direction = instance_port.direction

                # Count port directions on this net
                port_directions[net_direction] += 1

                # Check bus index is valid is present
                if port.idx is not None:
                    assert instance_port.bus is not None

                    if instance_port.bus.start <= instance_port.bus.end:
                        # Little-endian
                        assert port.idx >= instance_port.bus.start, (
                            instance_cell_name, port.idx,
                            instance_port.bus.start, instance_port.bus.end)
                        assert port.idx <= instance_port.bus.end, (
                            instance_cell_name, port.idx,
                            instance_port.bus.start, instance_port.bus.end)
                    else:
                        # Big-endian
                        assert port.idx <= instance_port.bus.start, (
                            instance_cell_name, port.idx,
                            instance_port.bus.start, instance_port.bus.end)
                        assert port.idx >= instance_port.bus.end, (
                            instance_cell_name, port.idx,
                            instance_port.bus.start, instance_port.bus.end)
                else:
                    assert instance_port.bus is None, (netname, port)

            if port_directions[Direction.Inout] == 0:
                assert port_directions[Direction.Input] in [
                    0, 1
                ], (netname, port_directions)
            else:
                # TODO: Not sure how to handle this case?
                # Should only have 0 input?
                assert port_directions[Direction.Input] == 0

    return master_cell_list.keys()
