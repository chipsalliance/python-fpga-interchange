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
""" Implements routines for converting FPGA interchange capnp files to models.

The models are implemented in python in fpga_interchange.logical_netlist and
fpga_interchange.physical_netlist.

LogicalNetlistBuilder - Internal helper class for constructing logical netlist
                        format.  Recommend use is to first construct logical
                        netlist using classes from logical_netlist module
                        and calling Interchange.output_logical_netlist.

output_logical_netlist - Implements conversion of classes from logical_netlist
                         module to FPGA interchange logical netlist format.
                         This function requires LogicalNetlist schema loaded,
                         recommend to use Interchange class to load schemas
                         from interchange schema directory, and then invoke
                         Interchange.output_logical_netlist.

PhysicalNetlistBuilder - Internal helper class for constructing physical
                         netlist format.

output_physical_netlist - Implements conversion of classes from physicla
                         module to FPGA interchange physical netlist format.
                         This function requires PhysicalNetlist schema loaded,
                         recommend to use Interchange class to load schemas
                         from interchange schema directory, and then invoke
                         Interchange.output_interchange.

Interchange - Class that handles loading capnp schemas.

"""
import capnp
import capnp.lib.capnp

capnp.remove_import_hook()
import enum
import gzip
import os.path
from .logical_netlist import check_logical_netlist, LogicalNetlist, Cell, \
        CellInstance, Library, Direction
from .physical_netlist import PhysicalNetlist, PhysicalCellType, \
        PhysicalNetType, PhysicalBelPin, PhysicalSitePin, PhysicalSitePip, \
        PhysicalPip, PhysicalNet, Placement
from .device_resources import DeviceResources

# Flag indicating use of Packed Cap'n Proto Serialization
IS_PACKED = False


class CompressionFormat(enum.Enum):
    UNCOMPRESSED = 0
    GZIP = 1


# Flag indicating that files are gziped on output
DEFAULT_COMPRESSION_TYPE = CompressionFormat.GZIP

# Set traversal limit to maximum to effectively disable.
NO_TRAVERSAL_LIMIT = 2**63 - 1

NESTING_LIMIT = 256

# Level 6 is much faster than level 9, but still has a reasonable compression
# level.
#
# From man page:
#  The default compression level is -6 (that is, biased towards high
#  compression at expense of speed).
#
DEFAULT_COMPRESSION = 6


def read_capnp_file(capnp_schema,
                    f_in,
                    compression_format=DEFAULT_COMPRESSION_TYPE,
                    is_packed=IS_PACKED):
    """ Read file to a capnp object.

    is_gzipped - bool
        Is output GZIP'd?

    is_packed - bool
        Is capnp file in packed or unpacked in its encoding?

    """
    if compression_format == CompressionFormat.GZIP:
        f_comp = gzip.GzipFile(fileobj=f_in, mode='rb')
        if is_packed:
            return capnp_schema.from_bytes_packed(
                f_comp.read(),
                traversal_limit_in_words=NO_TRAVERSAL_LIMIT,
                nesting_limit=NESTING_LIMIT)
        else:
            return capnp_schema.from_bytes(
                f_comp.read(),
                traversal_limit_in_words=NO_TRAVERSAL_LIMIT,
                nesting_limit=NESTING_LIMIT)
    else:
        assert compression_format == CompressionFormat.UNCOMPRESSED
        if is_packed:
            return capnp_schema.read_packed(
                f_in, traversal_limit_in_words=NO_TRAVERSAL_LIMIT)
        else:
            return capnp_schema.read(
                f_in, traversal_limit_in_words=NO_TRAVERSAL_LIMIT)


def write_capnp_file(capnp_obj,
                     f_out,
                     compression_format=DEFAULT_COMPRESSION_TYPE,
                     is_packed=IS_PACKED):
    """ Write capnp object to file.

    is_gzipped - bool
        Is output GZIP'd?

    is_packed - bool
        Should output capnp file be packed or unpacked in its encoding?

    """
    if compression_format == CompressionFormat.GZIP:
        with gzip.GzipFile(
                fileobj=f_out, mode='wb',
                compresslevel=DEFAULT_COMPRESSION) as f:
            if is_packed:
                f.write(capnp_obj.to_bytes_packed())
            else:
                f.write(capnp_obj.to_bytes())
    else:
        assert compression_format == CompressionFormat.UNCOMPRESSED
        if is_packed:
            capnp_obj.write_packed(f_out)
        else:
            capnp_obj.write(f_out)


class LogicalNetlistBuilder():
    """ Builder class for LogicalNetlist capnp format.

    The total number of cells, ports, cell instances should be known prior to
    calling the constructor for LogicalNetlistBuilder.

    logical_netlist_schema - Loaded logical netlist schema.
    name (str) - Name of logical netlist.
    cell_count (int) - Total number of cells in all libraries for this file.
    port_count (int) - Total number of cell ports in all cells in all
                       libraries for this file.
    cell_instance_count (int) - Total number of cell instances in all cells
                                in all libraries for this file.
    property_map (dict) - Root level property map for the netlist.

    indexed_strings (list of str, optional) - If provided, this string list
        is used to store strings, instead of LogicalNetlist.strList.

        This is useful when embedding LogicalNetlist in other schemas.

    """

    def __init__(self,
                 logical_netlist_schema,
                 name,
                 cell_count,
                 port_count,
                 cell_instance_count,
                 property_map,
                 indexed_strings=None):
        self.logical_netlist_schema = logical_netlist_schema
        self.logical_netlist = self.logical_netlist_schema.Netlist.new_message(
        )

        self.logical_netlist.name = name

        if indexed_strings is None:
            self.own_string_list = True
            self.string_map = {}
            self.string_list = []
        else:
            # An external string list is being provided.  Use that list (and
            # update it), and initialize the string_map with that initial list.
            self.own_string_list = False
            self.string_list = indexed_strings
            self.string_map = {}
            for idx, s in enumerate(self.string_list):
                self.string_map[s] = idx

        self.cell_idx = 0
        self.cell_count = cell_count
        self.cell_decls = self.logical_netlist.init("cellDecls", cell_count)
        self.cells = self.logical_netlist.init("cellList", cell_count)

        self.port_idx = 0
        self.port_count = port_count
        self.logical_netlist.init("portList", port_count)
        self.ports = self.logical_netlist.portList

        self.cell_instance_idx = 0
        self.cell_instance_count = cell_instance_count
        self.logical_netlist.init("instList", cell_instance_count)
        self.cell_instances = self.logical_netlist.instList

        self.create_property_map(self.logical_netlist.propMap, property_map)

    def next_cell(self):
        """ Return next logical_netlist.Cell pycapnp object and it's index. """
        assert self.cell_idx < self.cell_count

        cell_decl = self.cell_decls[self.cell_idx]
        cell = self.cells[self.cell_idx]
        cell_idx = self.cell_idx
        cell.index = cell_idx
        self.cell_idx += 1

        return cell_idx, cell, cell_decl

    def get_cell(self, cell_idx):
        """ Get logical_netlist.Cell pycapnp object at given index. """
        return self.logical_netlist.cellList[cell_idx]

    def next_port(self):
        """ Return next logical_netlist.Port pycapnp object and it's index. """
        assert self.port_idx < self.port_count
        port = self.ports[self.port_idx]
        port_idx = self.port_idx
        self.port_idx += 1

        return port_idx, port

    def next_cell_instance(self):
        """ Return next logical_netlist.CellInstance pycapnp object and it's index. """
        assert self.cell_instance_idx < self.cell_instance_count
        cell_instance = self.cell_instances[self.cell_instance_idx]
        cell_instance_idx = self.cell_instance_idx
        self.cell_instance_idx += 1

        return cell_instance_idx, cell_instance

    def string_id(self, s):
        """ Intern string into file, and return its StringIdx. """
        assert isinstance(s, str)

        if s not in self.string_map:
            self.string_map[s] = len(self.string_list)
            self.string_list.append(s)

        return self.string_map[s]

    def finish_encode(self):
        """ Completes the encoding of the logical netlist and returns root pycapnp object.

        Invoke after all cells, ports and cell instances have been populated
        with data.

        Returns completed logical_netlist.Netlist pycapnp object.

        """

        if self.own_string_list:
            self.logical_netlist.init('strList', len(self.string_list))

            for idx, s in enumerate(self.string_list):
                self.logical_netlist.strList[idx] = s

        return self.logical_netlist

    def create_property_map(self, property_map, d):
        """ Create a property_map from a python dictionary for this LogicalNetlist file.

        property_map (logical_netlist.PropertyMap pycapnp object) - Pycapnp
            object to write property map.
        d (dict-like) - Dictionary to convert to property map.
                        Keys must be strings.  Values can be strings, ints or
                        bools.

        """
        entries = property_map.init('entries', len(d))
        for entry, (k, v) in zip(entries, d.items()):
            assert isinstance(k, str)
            entry.key = self.string_id(k)

            if isinstance(v, str):
                if v[0] == '"' and v[-1] == '"':
                    v = v[1:-1]
                entry.textValue = self.string_id(v)
            elif isinstance(v, bool):
                entry.boolValue = v
            elif isinstance(v, int):
                entry.intValue = v
            else:
                assert False, "Unknown type of value {}, type = {}".format(
                    repr(v), type(v))

    def get_top_cell_instance(self):
        """ Return the top cell instance from the LogicalNetlist. """
        return self.logical_netlist.topInst


def output_logical_netlist(logical_netlist_schema,
                           libraries,
                           name,
                           top_instance_name,
                           top_instance,
                           view="netlist",
                           property_map={},
                           indexed_strings=None):
    """ Convert logical_netlist.Library python classes to a FPGA interchange LogicalNetlist capnp.

    logical_netlist_schema - logical_netlist schema.
    libraries (dict) - Dict of str to logical_netlist.Library python classes.
    top_level_cell (str) - Name of Cell to instance at top level
    top_level_name (str) - Name of top level cell instance
    view (str) - EDIF internal constant.
    property_map - PropertyMap for top level cell instance

    """

    # Sanity that the netlist libraries are complete and consistent, also
    # output master cell list.
    master_cell_list = check_logical_netlist(libraries)

    # Make sure top level cell is in the master cell list.
    assert top_instance is None or top_instance.cell_name in master_cell_list

    # Count cell, port and cell instance counts to enable pre-allocation of
    # capnp arrays.
    cell_count = 0
    port_count = 0
    cell_instance_count = 0
    for lib in libraries.values():
        cell_count += len(lib.cells)
        for cell in lib.cells.values():
            port_count += len(cell.ports)
            cell_instance_count += len(cell.cell_instances)

    logical_netlist = LogicalNetlistBuilder(
        logical_netlist_schema=logical_netlist_schema,
        name=name,
        cell_count=cell_count,
        port_count=port_count,
        cell_instance_count=cell_instance_count,
        property_map=property_map,
        indexed_strings=indexed_strings)

    # Assign each python Cell objects in libraries to capnp
    # logical_netlist.Cell objects, and record the cell index for use with
    # cell instances later.
    #
    # Ports can also be converted now, do that too.  Build a map of cell name
    # and port name to port objects for use on constructing cell nets.
    cell_name_to_idx = {}
    ports = {}

    for library, lib in libraries.items():
        library_id = logical_netlist.string_id(library)
        for cell in lib.cells.values():
            assert cell.name not in cell_name_to_idx
            cell_idx, cell_obj, cell_decl = logical_netlist.next_cell()

            cell_decl.name = logical_netlist.string_id(cell.name)
            cell_decl.view = logical_netlist.string_id(cell.view)
            cell_decl.lib = library_id

            cell_name_to_idx[cell.name] = cell_idx

            logical_netlist.create_property_map(cell_decl.propMap,
                                                cell.property_map)

            cell_decl.init('ports', len(cell.ports))
            for idx, (port_name, port) in enumerate(cell.ports.items()):
                port_idx, port_obj = logical_netlist.next_port()
                ports[cell.name, port_name] = (port_idx, port)
                cell_decl.ports[idx] = port_idx

                port_obj.dir = logical_netlist_schema.Netlist.Direction.__dict__[
                    port.direction.name.lower()]
                logical_netlist.create_property_map(port_obj.propMap,
                                                    port.property_map)
                if port.bus is not None:
                    port_obj.name = logical_netlist.string_id(port_name)
                    bus = port_obj.init('bus')
                    bus.busStart = port.bus.start
                    bus.busEnd = port.bus.end
                else:
                    port_obj.name = logical_netlist.string_id(port_name)
                    port_obj.bit = None

    # Now that each cell type has been assigned a cell index, add cell
    # instances to cells as needed.
    for lib in libraries.values():
        for cell in lib.cells.values():
            cell_obj = logical_netlist.get_cell(cell_name_to_idx[cell.name])

            # Save mapping of cell instance name to cell instance index for
            # cell net construction
            cell_instances = {}

            cell_obj.init('insts', len(cell.cell_instances))
            for idx, (cell_instance_name,
                      cell_instance) in enumerate(cell.cell_instances.items()):
                cell_instance_idx, cell_instance_obj = logical_netlist.next_cell_instance(
                )
                cell_instances[cell_instance_name] = cell_instance_idx

                cell_instance_obj.name = logical_netlist.string_id(
                    cell_instance_name)
                logical_netlist.create_property_map(cell_instance_obj.propMap,
                                                    cell_instance.property_map)
                cell_instance_obj.view = logical_netlist.string_id(
                    cell_instance.view)
                cell_instance_obj.cell = cell_name_to_idx[cell_instance.
                                                          cell_name]

                cell_obj.insts[idx] = cell_instance_idx

            cell_obj.init('nets', len(cell.nets))
            for net_obj, (netname, net) in zip(cell_obj.nets,
                                               cell.nets.items()):
                net_obj.name = logical_netlist.string_id(netname)
                logical_netlist.create_property_map(net_obj.propMap,
                                                    net.property_map)

                net_obj.init('portInsts', len(net.ports))

                for port_obj, port in zip(net_obj.portInsts, net.ports):
                    if port.instance_name is not None:
                        # If port.instance_name is not None, then this is a
                        # cell instance port connection.
                        instance_cell_name = cell.cell_instances[
                            port.instance_name].cell_name
                        port_obj.inst = cell_instances[port.instance_name]
                        port_obj.port, port_pyobj = ports[instance_cell_name,
                                                          port.name]
                    else:
                        # If port.instance_name is None, then this is a cell
                        # port connection
                        port_obj.extPort = None
                        port_obj.port, port_pyobj = ports[cell.name, port.name]

                    # Handle bussed port annotations
                    if port.idx is not None:
                        port_obj.busIdx.idx = port_pyobj.encode_index(port.idx)
                    else:
                        port_obj.busIdx.singleBit = None

    if top_instance is not None:
        top_level_cell_instance = logical_netlist.get_top_cell_instance()
        # Convert the top level cell now that the libraries have been converted.
        top_level_cell_instance.name = logical_netlist.string_id(
            top_instance_name)
        top_level_cell_instance.cell = cell_name_to_idx[top_instance.cell_name]
        top_level_cell_instance.view = logical_netlist.string_id(
            top_instance.view)
        logical_netlist.create_property_map(top_level_cell_instance.propMap,
                                            top_instance.property_map)

    return logical_netlist.finish_encode()


class PhysicalNetlistBuilder():
    """ Builder class for PhysicalNetlist capnp format.

    physical_netlist_schema - Loaded physical netlist schema.

    """

    def __init__(self, physical_netlist_schema):
        self.physical_netlist_schema = physical_netlist_schema

    def init_string_map(self):
        self.string_map = {}
        self.string_list = []

    def string_id(self, s):
        """ Intern string into file, and return its StringIdx. """
        assert isinstance(s, str)

        if s not in self.string_map:
            self.string_map[s] = len(self.string_list)
            self.string_list.append(s)

        return self.string_map[s]

    def encode(self, phys_netlist):
        """ Completes the encoding of the physical netlist and returns root pycapnp object.

        Invoke after all placements, physical cells and physical nets have
        been added.

        Returns completed physical_netlist.PhysNetlist pycapnp object.

        """

        self.init_string_map()

        physical_netlist = self.physical_netlist_schema.PhysNetlist.new_message(
        )
        physical_netlist.part = phys_netlist.part
        physical_netlist.init('placements', len(phys_netlist.placements))
        placements = physical_netlist.placements
        for idx, placement in enumerate(phys_netlist.placements):
            placement_obj = placements[idx]

            placement_obj.cellName = self.string_id(placement.cell_name)
            placement_obj.type = self.string_id(placement.cell_type)

            placement_obj.site = self.string_id(placement.site)
            placement_obj.bel = self.string_id(placement.bel)
            placement_obj.isSiteFixed = True
            placement_obj.isBelFixed = True

            if placement.other_bels:
                placement_obj.init('otherBels', len(placement.other_bels))
                other_bels_obj = placement_obj.otherBels
                for idx, s in enumerate(placement.other_bels):
                    other_bels_obj[idx] = self.string_id(s)

            placement_obj.init('pinMap', len(placement.pins))
            pin_map = placement_obj.pinMap
            for idx, pin in enumerate(placement.pins):
                pin_map[idx].cellPin = self.string_id(pin.cell_pin)
                pin_map[idx].belPin = self.string_id(pin.bel_pin)
                if pin.bel is None:
                    pin_map[idx].bel = placement_obj.bel
                else:
                    pin_map[idx].bel = self.string_id(pin.bel)
                pin_map[idx].isFixed = True

                if pin.other_cell_type:
                    assert pin.other_cell_name is not None
                    pin.otherCell.multiCell = self.string_id(
                        pin.other_cell_name)
                    pin.otherCell.multiType = self.string_id(
                        pin.other_cell_type)

        physical_netlist.init('physNets', len(phys_netlist.nets))
        nets = physical_netlist.physNets
        for idx, net in enumerate(phys_netlist.nets):
            net_obj = nets[idx]

            net_obj.name = self.string_id(net.name)
            net_obj.init('sources', len(net.sources))
            for root_obj, root in zip(net_obj.sources, net.sources):
                root.output_interchange(root_obj, self.string_id)

            net_obj.init('stubs', len(net.stubs))
            for stub_obj, stub in zip(net_obj.stubs, net.stubs):
                stub.output_interchange(stub_obj, self.string_id)

            net_obj.type = self.physical_netlist_schema.PhysNetlist.NetType.__dict__[
                net.type.name.lower()]

        physical_netlist.init('physCells', len(phys_netlist.physical_cells))
        physical_cells = physical_netlist.physCells
        for idx, (cell_name,
                  cell_type) in enumerate(phys_netlist.physical_cells.items()):
            physical_cell = physical_cells[idx]
            physical_cell.cellName = self.string_id(cell_name)
            physical_cell.physType = self.physical_netlist_schema.PhysNetlist.PhysCellType.__dict__[
                cell_type.name.lower()]

        physical_netlist.init('properties', len(phys_netlist.properties))
        properties = physical_netlist.properties
        for idx, (k, v) in enumerate(phys_netlist.properties.items()):
            properties[idx].key = self.string_id(k)
            properties[idx].value = self.string_id(v)

        physical_netlist.init('siteInsts', len(phys_netlist.site_instances))
        site_instances = physical_netlist.siteInsts
        for idx, (k, v) in enumerate(phys_netlist.site_instances.items()):
            site_instances[idx].site = self.string_id(k)
            site_instances[idx].type = self.string_id(v)

        physical_netlist.init('strList', len(self.string_list))

        for idx, s in enumerate(self.string_list):
            physical_netlist.strList[idx] = s

        return physical_netlist


def output_physical_netlist(physical_netlist, physical_netlist_schema):
    builder = PhysicalNetlistBuilder(physical_netlist_schema)
    return builder.encode(physical_netlist)


def first_upper(s):
    return s[0].upper() + s[1:]


def to_logical_netlist(netlist_capnp, strs=None):
    # name     @0 : Text;
    # propMap  @1 : PropertyMap;
    # topInst  @2 : CellInstance;
    # strList  @3 : List(Text);
    # cellList @4 : List(Cell);
    # portList @5 : List(Port);
    # instList @6 : List(CellInstance);

    if strs is None:
        strs = [s for s in netlist_capnp.strList]

    libraries = {}

    def convert_property_map(prop_map):
        out = {}

        for prop in prop_map.entries:
            key = strs[prop.key]
            if prop.which() == 'textValue':
                value = strs[prop.textValue]
            elif prop.which() == 'intValue':
                value = prop.intValue
            else:
                assert prop.which() == 'boolValue'
                value = prop.boolValue
            out[key] = value

        return out

    def convert_cell_instance(cell_instance_capnp):
        prop_map = convert_property_map(cell_instance_capnp.propMap)

        name = strs[cell_instance_capnp.name]
        return name, CellInstance(
            view=strs[cell_instance_capnp.view],
            cell_name=strs[netlist_capnp.cellDecls[cell_instance_capnp.cell].
                           name],
            property_map=prop_map,
            capnp_name=cell_instance_capnp.cell)

    for cell_capnp in netlist_capnp.cellList:
        cell_decl = netlist_capnp.cellDecls[cell_capnp.index]
        cell = Cell(
            name=strs[cell_decl.name],
            capnp_index=cell_capnp.index,
            property_map=convert_property_map(cell_decl.propMap),
        )
        cell.view = strs[cell_decl.view]

        for inst in cell_capnp.insts:
            cell_instance_name, cell_instance = convert_cell_instance(
                netlist_capnp.instList[inst])
            cell.cell_instances[cell_instance_name] = cell_instance

        for port_idx in cell_decl.ports:
            port = netlist_capnp.portList[port_idx]
            port_name = strs[port.name]
            direction = Direction[first_upper(str(port.dir))]
            prop_map = convert_property_map(port.propMap)
            if port.which() == 'bit':
                cell.add_port(
                    name=port_name, direction=direction, property_map=prop_map)
            else:
                assert port.which() == 'bus'
                cell.add_bus_port(
                    name=port_name,
                    direction=direction,
                    property_map=prop_map,
                    start=port.bus.busStart,
                    end=port.bus.busEnd)

        for net in cell_capnp.nets:
            net_name = strs[net.name]
            cell.add_net(
                name=net_name,
                property_map=convert_property_map(net.propMap),
            )

            for port_inst in net.portInsts:
                port_capnp = netlist_capnp.portList[port_inst.port]
                port_name = strs[port_capnp.name]

                if port_inst.busIdx.which() == 'singleBit':
                    idx = None
                else:
                    assert port_inst.busIdx.which() == 'idx'
                    assert port_capnp.which() == 'bus'
                    bus = port_capnp.bus
                    if bus.busStart <= bus.busEnd:
                        idx = port_inst.busIdx.idx + bus.busStart
                    else:
                        idx = bus.busStart - port_inst.busIdx.idx

                if port_inst.which() == 'extPort':
                    cell.connect_net_to_cell_port(
                        net_name=net_name, port=port_name, idx=idx)
                else:
                    assert port_inst.which() == 'inst'
                    instance_name = strs[netlist_capnp.instList[port_inst.
                                                                inst].name]
                    cell.connect_net_to_instance(
                        net_name=net_name,
                        instance_name=instance_name,
                        port=port_name,
                        idx=idx)

        library = strs[cell_decl.lib]
        if library not in libraries:
            libraries[library] = Library(name=library)
        libraries[library].add_cell(cell)

    top_instance_name, top_instance = convert_cell_instance(
        netlist_capnp.topInst)
    return LogicalNetlist(
        name=netlist_capnp.name,
        property_map=convert_property_map(netlist_capnp.propMap),
        top_instance_name=top_instance_name,
        top_instance=top_instance,
        libraries=libraries)


def to_physical_netlist(phys_netlist_capnp):
    strs = [s for s in phys_netlist_capnp.strList]

    properties = {}
    for prop in phys_netlist_capnp.properties:
        properties[strs[prop.key]] = strs[prop.value]

    phys_netlist = PhysicalNetlist(phys_netlist_capnp.part, properties)

    for site_instance in phys_netlist_capnp.siteInsts:
        phys_netlist.add_site_instance(strs[site_instance.site],
                                       strs[site_instance.type])

    for physical_cell in phys_netlist_capnp.physCells:
        phys_netlist.add_physical_cell(
            strs[physical_cell.cellName], PhysicalCellType[first_upper(
                str(physical_cell.physType))])

    def convert_route_segment(route_segment_capnp):
        which = route_segment_capnp.which()
        if which == 'belPin':
            bel_pin = route_segment_capnp.belPin
            return PhysicalBelPin(
                site=strs[bel_pin.site],
                bel=strs[bel_pin.bel],
                pin=strs[bel_pin.pin])
        elif which == 'sitePin':
            site_pin = route_segment_capnp.sitePin
            return PhysicalSitePin(
                site=strs[site_pin.site], pin=strs[site_pin.pin])
        elif which == 'pip':
            # TODO: Shouldn't be discard isFixed field
            pip = route_segment_capnp.pip

            site = strs[pip.site] if pip.which() == 'site' else None

            return PhysicalPip(
                tile=strs[pip.tile],
                wire0=strs[pip.wire0],
                wire1=strs[pip.wire1],
                forward=pip.forward,
                site=site)
        else:
            assert which == 'sitePIP'
            # TODO: Shouldn't be discard isFixed and inverts, isInverting
            # fields
            site_pip = route_segment_capnp.sitePIP
            return PhysicalSitePip(
                site=strs[site_pip.site],
                bel=strs[site_pip.bel],
                pin=strs[site_pip.pin],
                is_inverting=site_pip.isInverting)

    def convert_route_branch(route_branch_capnp):
        obj = convert_route_segment(route_branch_capnp.routeSegment)

        for branch in route_branch_capnp.branches:
            obj.branches.append(convert_route_branch(branch))

        return obj

    def convert_net(net_capnp):
        sources = []
        for source_capnp in net_capnp.sources:
            sources.append(convert_route_branch(source_capnp))

        stubs = []
        for stub_capnp in net_capnp.stubs:
            stubs.append(convert_route_branch(stub_capnp))

        return PhysicalNet(
            name=strs[net_capnp.name],
            type=PhysicalNetType[first_upper(str(net_capnp.type))],
            sources=sources,
            stubs=stubs)

    null_net = convert_net(phys_netlist_capnp.nullNet)
    assert len(null_net.sources) == 0
    phys_netlist.set_null_net(null_net.stubs)

    for physical_net in phys_netlist_capnp.physNets:
        net = convert_net(physical_net)
        phys_netlist.add_physical_net(
            net_name=net.name,
            sources=net.sources,
            stubs=net.stubs,
            net_type=net.type)

    for placement_capnp in phys_netlist_capnp.placements:
        # TODO: Shouldn't be discarding isBelFixed/isSiteFixed/altSiteType
        placement = Placement(
            cell_type=strs[placement_capnp.type],
            cell_name=strs[placement_capnp.cellName],
            site=strs[placement_capnp.site],
            bel=strs[placement_capnp.bel],
        )

        for pin_map in placement_capnp.pinMap:
            # TODO: Shouldn't be discarding isFixed
            other_cell_name = None
            other_cell_type = None

            if pin_map.which() == 'otherCell':
                other_cell = pin_map.otherCell
                other_cell_name = strs[other_cell.multiCell]
                other_cell_type = strs[other_cell.multiType]

            placement.add_bel_pin_to_cell_pin(
                bel=strs[pin_map.bel],
                bel_pin=strs[pin_map.belPin],
                cell_pin=strs[pin_map.cellPin],
                other_cell_type=other_cell_type,
                other_cell_name=other_cell_name)

        for other_bel in placement_capnp.otherBels:
            placement.other_bels.add(strs[other_bel])

        phys_netlist.add_placement(placement)

    return phys_netlist


class Interchange():
    def __init__(self, schema_directory):

        search_path = [os.path.dirname(os.path.dirname(capnp.__file__))]
        if 'CONDA_PREFIX' in os.environ:
            search_path.append(
                os.path.join(os.environ['CONDA_PREFIX'], 'include'))

        if 'CAPNP_PATH' in os.environ:
            search_path.append(os.environ['CAPNP_PATH'])

        for path in ['/usr/local/include', '/usr/include']:
            if os.path.exists(path):
                search_path.append(path)

        self.references_schema = capnp.load(
            os.path.join(schema_directory, 'References.capnp'),
            imports=search_path)
        self.logical_netlist_schema = capnp.load(
            os.path.join(schema_directory, 'LogicalNetlist.capnp'),
            imports=search_path)
        self.physical_netlist_schema = capnp.load(
            os.path.join(schema_directory, 'PhysicalNetlist.capnp'),
            imports=search_path)
        self.device_resources_schema = capnp.load(
            os.path.join(schema_directory, 'DeviceResources.capnp'),
            imports=search_path)

    def output_logical_netlist(self, *args, **kwargs):
        return output_logical_netlist(
            logical_netlist_schema=self.logical_netlist_schema,
            *args,
            **kwargs)

    def output_physical_netlist(self, *args, **kwargs):
        return output_physical_netlist(
            physical_netlist_schema=self.physical_netlist_schema,
            *args,
            **kwargs)

    def read_logical_netlist_raw(self,
                                 f,
                                 compression_format=DEFAULT_COMPRESSION_TYPE,
                                 is_packed=IS_PACKED):
        return read_capnp_file(self.logical_netlist_schema.Netlist, f,
                               compression_format, is_packed)

    def read_logical_netlist(self,
                             f,
                             compression_format=DEFAULT_COMPRESSION_TYPE,
                             is_packed=IS_PACKED):
        return to_logical_netlist(
            read_capnp_file(self.logical_netlist_schema.Netlist, f,
                            compression_format, is_packed))

    def read_physical_netlist(self,
                              f,
                              compression_format=DEFAULT_COMPRESSION_TYPE,
                              is_packed=IS_PACKED):
        return to_physical_netlist(
            read_capnp_file(self.physical_netlist_schema.PhysNetlist, f,
                            compression_format, is_packed))

    def read_physical_netlist_raw(self,
                                  f,
                                  compression_format=DEFAULT_COMPRESSION_TYPE,
                                  is_packed=IS_PACKED):
        return read_capnp_file(self.physical_netlist_schema.PhysNetlist, f,
                               compression_format, is_packed)

    def read_device_resources_raw(self,
                                  f,
                                  compression_format=DEFAULT_COMPRESSION_TYPE,
                                  is_packed=IS_PACKED):
        return read_capnp_file(self.device_resources_schema.Device, f,
                               compression_format, is_packed)

    def read_device_resources(self,
                              f,
                              compression_format=DEFAULT_COMPRESSION_TYPE,
                              is_packed=IS_PACKED):
        return DeviceResources(
            read_capnp_file(self.device_resources_schema.Device, f,
                            compression_format, is_packed))
