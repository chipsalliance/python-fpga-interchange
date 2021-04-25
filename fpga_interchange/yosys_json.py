#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2021  The SymbiFlow Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
""" Utility for converting yosys json to logical netlist. """
import argparse
import json
import re

from fpga_interchange.interchange_capnp import Interchange, write_capnp_file
from fpga_interchange.logical_netlist import LogicalNetlist, Cell, \
        CellInstance, Direction, Library
from fpga_interchange.parameter_definitions import ParameterFormat


def is_bus(bits, offset, upto):
    """ Returns true if this port/net is a bus.

    >>> is_bus([2], offset=0, upto=0)
    False
    >>> is_bus([2, 3], offset=0, upto=0)
    True
    >>> is_bus([2], offset=1, upto=0)
    True
    >>> is_bus([2], offset=0, upto=1)
    True

    """
    return len(bits) > 1 or offset != 0 or upto != 0


def interp_yosys_net(bits, offset, upto):
    """ Convert yosys json bits/offset/upto into (net selection, net bit)

    Yosys JSON encodes multi-bit nets as a triple of bits / offset / upto:
     - bits is a list of net bits that uniquely identifies what net the
       signal is tied too.
     - offset (default: 0) is the net offset.  Examples:

         wire [7:4] ex1; // offset = 4
         wire [3:0] ex2; // offset = 0 (implicitly)
         wire [0:3] ex3; // offset = 0 (implicitly)
         wire [5:7] ex4; // offset = 5

    - upto (default: 0) determines if the net is count up or count down.

         wire [7:4] ex1; // upto = 0 (implicitly)
         wire [3:0] ex2; // upto = 0 (implicitly)
         wire [0:3] ex3; // upto = 1
         wire [5:7] ex4; // upto = 1

    >>> bits = [2, 3, 4, 5]
    >>> tuple(interp_yosys_net(bits, offset=0, upto=0))
    ((0, 2), (1, 3), (2, 4), (3, 5))
    >>> tuple(interp_yosys_net(bits, offset=4, upto=0))
    ((4, 2), (5, 3), (6, 4), (7, 5))
    >>> tuple(interp_yosys_net(bits, offset=0, upto=1))
    ((3, 2), (2, 3), (1, 4), (0, 5))
    >>> tuple(interp_yosys_net(bits, offset=4, upto=1))
    ((7, 2), (6, 3), (5, 4), (4, 5))

    """
    if not upto:
        for idx, bit in enumerate(bits):
            yield idx + offset, bit
    else:
        for idx, bit in enumerate(bits):
            yield offset + (len(bits) - 1) - idx, bit


def create_unique_name(names, base_name):
    if base_name not in names:
        return base_name

    idx = 0
    while True:
        name = '{}_{}'.format(base_name, idx)
        if name not in names:
            return name

        idx += 1


def make_vcc_cell(cell, module_data, consts):
    cell_names = set(cell.cell_instances.keys()) | set(
        module_data['cells'].keys())
    vcc_cell = create_unique_name(cell_names, '$__vcc')
    cell.add_cell_instance(name=vcc_cell, cell_name=consts.VCC_CELL_TYPE)

    return vcc_cell


def make_gnd_cell(cell, module_data, consts):
    cell_names = set(cell.cell_instances.keys()) | set(
        module_data['cells'].keys())
    gnd_cell = create_unique_name(cell_names, '$__gnd')
    cell.add_cell_instance(name=gnd_cell, cell_name=consts.GND_CELL_TYPE)

    return gnd_cell


# This regex matches the case when Yosys JSON parameters add an extra space.
TRAILING_SPACE_RE = re.compile('[01xz]* +$')


def check_trailing_space(value):
    """ Some strings in Yosys JSON have a trailing space.  Remove it if needed. """

    m = TRAILING_SPACE_RE.match(value)
    if m is not None:
        return value[:-1]
    else:
        return value


def yosys_encodes_as_bitvec(param):
    # The parameter types that Yosys encodes as a bitvector
    return param.string_format in [
        ParameterFormat.BOOLEAN,
        ParameterFormat.INTEGER,
        ParameterFormat.VERILOG_BINARY,
        ParameterFormat.VERILOG_HEX,
    ]


def convert_parameters(device, cell, cell_type, property_map):
    """ Convert cell parameters to match expression type from default. """
    for name in property_map.keys():
        definition = device.get_parameter_definition(cell_type, name)
        if definition is None:
            # This parameter doesn't have a special definition, don't touch it.
            property_map[name] = check_trailing_space(property_map[name])
            continue

        if not yosys_encodes_as_bitvec(definition):
            # Non-integer like parameters come from yosys as a string, leave
            # them alone.
            property_map[name] = check_trailing_space(property_map[name])
            continue

        yosys_value = property_map[name]
        try:
            integer_value = int(yosys_value, 2)
        except ValueError as e:
            raise ValueError(
                'When converting cell {} of type {}, property {} should be integer-like, but was {}\n{}'
                .format(cell, cell_type, name, yosys_value, e))

        property_map[name] = definition.encode_integer(integer_value)


def convert_cell(device, module_name, module_data, library, libraries, modules,
                 verbose, errors, consts):
    for cell_name, cell_data in module_data['cells'].items():
        # Don't import modules that are missing children, they likely aren't
        # important.
        if cell_data['type'] not in modules:
            errors[
                module_name] = 'Failed to import cell type {} because it has a undefined cell {}'.format(
                    module_name, cell_data['type'])
            return

    property_map = {}
    if 'attributes' in module_data:
        property_map = module_data['attributes']

    cell = Cell(module_name, property_map)
    libraries[library].add_cell(cell)

    net_duplicate_names = {}

    def add_net(net_name, net_data, track_duplicates=False):
        property_map = {}
        if 'attributes' in net_data:
            property_map.update(net_data['attributes'])

        offset = net_data.get('offset', 0)
        upto = net_data.get('upto', 0)
        if is_bus(net_data['bits'], offset, upto):
            for bit_index, bit in interp_yosys_net(net_data['bits'], offset,
                                                   upto):
                name = '{}[{}]'.format(net_name, bit_index)
                cell.add_net(name, property_map)

                if bit == '0':
                    cell.connect_net_to_instance(
                        name, make_gnd_cell(cell, module_data, consts),
                        consts.GND_PORT)
                elif bit == '1':
                    cell.connect_net_to_instance(
                        name, make_vcc_cell(cell, module_data, consts),
                        consts.VCC_PORT)
                else:
                    assert isinstance(bit, int), bit

                    if bit in net_bits:
                        if track_duplicates:
                            net_duplicate_names[net_bits[bit]].append(name)
                        continue

                    assert bit not in net_bits, (module_name, bit,
                                                 net_bits.keys())
                    net_bits[bit] = name
                    net_duplicate_names[name] = []
        else:
            cell.add_net(net_name, property_map)

            bit = net_data['bits'][0]
            if bit == '0':
                cell.connect_net_to_instance(
                    net_name, make_gnd_cell(cell, module_data, consts),
                    consts.GND_PORT)
            elif bit == '1':
                cell.connect_net_to_instance(
                    net_name, make_vcc_cell(cell, module_data, consts),
                    consts.VCC_PORT)
            else:
                assert isinstance(bit, int)

                if bit in net_bits:
                    if track_duplicates:
                        net_duplicate_names[net_bits[bit]].append(net_name)
                    return

                assert bit not in net_bits, (module_name, bit, net_bits.keys())
                net_bits[bit] = net_name
                net_duplicate_names[net_name] = []

    net_bits = {}
    for net_name, net_data in module_data['netnames'].items():
        if net_name in module_data['ports']:
            continue

        if net_data.get('hide_name', 0):
            continue

        add_net(net_name, net_data, track_duplicates=False)

    for net_name, net_data in module_data['netnames'].items():
        if net_name not in module_data['ports']:
            continue

        add_net(net_name, net_data, track_duplicates=True)

    for net_name, net_data in module_data['netnames'].items():
        if net_data.get('hide_name', 0) != 1:
            continue

        add_net(net_name, net_data, track_duplicates=False)

    vcc_cell = None
    vcc_net = None

    gnd_cell = None
    gnd_net = None

    def get_net(bit):
        if bit == '0':
            nonlocal gnd_cell
            nonlocal gnd_net
            if gnd_cell is None:
                gnd_cell = make_gnd_cell(cell, module_data, consts)
                net_names = set(cell.nets.keys()) | set(
                    module_data['netnames'].keys())
                gnd_net = create_unique_name(net_names, '$__gnd_net')

                cell.add_net(gnd_net)
                cell.connect_net_to_instance(gnd_net, gnd_cell,
                                             consts.GND_PORT)

            return gnd_net
        elif bit == '1':
            nonlocal vcc_cell
            nonlocal vcc_net
            if vcc_cell is None:
                vcc_cell = make_vcc_cell(cell, module_data, consts)
                net_names = set(cell.nets.keys()) | set(
                    module_data['netnames'].keys())
                vcc_net = create_unique_name(net_names, '$__vcc_net')

                cell.add_net(vcc_net)
                cell.connect_net_to_instance(vcc_net, vcc_cell,
                                             consts.VCC_PORT)

            return vcc_net
        else:
            assert isinstance(bit, int)
            return net_bits[bit]

    for port_name, port_data in module_data['ports'].items():
        if port_data['direction'] == 'input':
            direction = Direction.Input
        elif port_data['direction'] == 'output':
            direction = Direction.Output
        else:
            assert port_data['direction'] == 'inout'
            direction = Direction.Inout

        property_map = {}
        if 'attributes' in port_data:
            property_map = port_data['attributes']

        offset = port_data.get('offset', 0)
        upto = port_data.get('upto', False)

        if is_bus(port_data['bits'], offset, upto):
            end = offset
            start = offset + len(port_data['bits']) - 1

            if upto:
                start, end = end, start

            cell.add_bus_port(
                name=port_name,
                direction=direction,
                start=start,
                end=end,
                property_map=property_map)

            for bit_index, bit in interp_yosys_net(port_data['bits'], offset,
                                                   upto):
                cell.connect_net_to_cell_port(
                    get_net(bit), port_name, bit_index)
        else:
            cell.add_port(
                name=port_name, direction=direction, property_map=property_map)
            cell.connect_net_to_cell_port(
                get_net(port_data['bits'][0]), port_name)

    for cell_name, cell_data in module_data['cells'].items():
        property_map = {}
        if 'attributes' in cell_data:
            property_map.update(cell_data['attributes'])

        if 'parameters' in cell_data:
            property_map.update(cell_data['parameters'])

        convert_parameters(device, cell_name, cell_data['type'], property_map)

        # Set default parameters if not already set from Yosys.
        device.add_default_parameters(cell_data['type'], property_map)

        cell.add_cell_instance(
            name=cell_name,
            cell_name=cell_data['type'],
            property_map=property_map)

        cell_type = modules[cell_data['type']]
        for port_name, bits in cell_data['connections'].items():
            port = cell_type['ports'][port_name]
            offset = port.get('offset', 0)
            upto = port.get('upto', False)

            if is_bus(bits, offset, upto):
                for bit_index, bit in interp_yosys_net(bits, offset, upto):
                    cell.connect_net_to_instance(
                        get_net(bit), cell_name, port_name, bit_index)
            else:
                cell.connect_net_to_instance(
                    get_net(bits[0]), cell_name, port_name)


def find_all_cell_types_from_module(module, modules, primitive_cells):
    """ Determine all of the cells types used in this module.

    This includes children of this module, and also includes primitive_cells.
    The primitive_cells lists is used to determine when this search should
    stop and not examine within a cell.  This is to prevent exposing yosys
    internal logic (e.g. specify cells) to the output logical netlist.

    Returns a set of all cell types uses within the specified module.

    """
    cells_in_module = set()

    assert module in modules, module

    module_data = modules[module]
    for cell_name, cell_data in module_data['cells'].items():
        cell_type = cell_data['type']

        cells_in_module.add(cell_type)

        if cell_type not in primitive_cells:
            cells_in_module |= find_all_cell_types_from_module(
                cell_type, modules, primitive_cells)

    return cells_in_module


def convert_yosys_json(device,
                       yosys_json,
                       top,
                       work_library='work',
                       verbose=False):
    """ Converts Yosys Netlist JSON to FPGA interchange logical netlist. """
    primitives = device.get_primitive_library()
    primitive_cells = primitives.get_master_cell_list()
    primitive_lib = {}
    for lib_name, lib in primitives.libraries.items():
        for cell in lib.cells.values():
            primitive_lib[cell.name] = lib_name

    consts = device.get_constants()

    name = top
    property_map = {}
    top_module = yosys_json['modules'][top]
    if 'attributes' in top_module:
        property_map.update(top_module['attributes'])

    top_instance_name = top
    top_instance = CellInstance(
        property_map=property_map, view='netlist', cell_name=top)

    libraries = {
        work_library: Library(work_library),
    }

    cells_used_in_top = find_all_cell_types_from_module(
        top, yosys_json['modules'], primitive_cells)
    cells_used_in_top.add(top)

    module_errors = {}
    for module_name, module_data in yosys_json['modules'].items():
        if module_name not in cells_used_in_top:
            if verbose:
                print('Skipping {} because it is an unused cell type'.format(
                    module_name))
            continue

        if module_name in primitive_cells:
            if verbose:
                print('Skipping {} because it is a library cell'.format(
                    module_name))
            continue

        convert_cell(device, module_name, module_data, work_library, libraries,
                     yosys_json['modules'], verbose, module_errors, consts)

    netlist = LogicalNetlist(
        name=name,
        property_map=property_map,
        top_instance_name=top_instance_name,
        top_instance=top_instance,
        libraries=libraries)

    required_cells = set()
    for lib_name, lib in netlist.libraries.items():
        for cell in lib.cells.values():
            for cell_instance in cell.cell_instances.values():
                required_cells.add(cell_instance.cell_name)

    required_cells -= set(netlist.get_master_cell_list().keys())

    for required_cell in sorted(required_cells):
        if required_cell not in primitive_cells:
            if required_cell in module_errors:
                raise RuntimeError(module_errors[required_cell])
            else:
                raise RuntimeError(
                    'Failed to find cell type {}'.format(required_cell))

        lib_name = primitive_lib[required_cell]
        if lib_name not in libraries:
            libraries[lib_name] = Library(lib_name)

        prim_cell = primitive_cells[required_cell]

        # Blackbox macro content, we only care about the primitive ports - the macro content is obtained from the chipdb
        prim_cell.cell_instances.clear()
        prim_cell.nets.clear()

        netlist.libraries[lib_name].add_cell(prim_cell)

    return netlist


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument('--schema_dir', required=True)
    parser.add_argument('--device', required=True)
    parser.add_argument('--top', required=True)
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument(
        '--library',
        default='work',
        help='Library to put non-primitive elements')
    parser.add_argument('yosys_json')
    parser.add_argument('netlist')

    args = parser.parse_args()

    with open(args.yosys_json) as f:
        yosys_json = json.load(f)

    assert 'modules' in yosys_json, yosys_json.keys()

    if args.top not in yosys_json['modules']:
        raise RuntimeError(
            'Could not find top module in yosys modules: {}'.format(', '.join(
                yosys_json['modules'].keys())))

    interchange = Interchange(args.schema_dir)

    with open(args.device, 'rb') as f:
        device = interchange.read_device_resources(f)

    netlist = convert_yosys_json(device, yosys_json, args.top, args.library,
                                 args.verbose)
    netlist_capnp = netlist.convert_to_capnp(interchange)

    with open(args.netlist, 'wb') as f:
        write_capnp_file(netlist_capnp, f)


if __name__ == "__main__":
    main()
