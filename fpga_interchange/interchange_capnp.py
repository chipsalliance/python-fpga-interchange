""" Implements models for generating FPGA interchange formats.

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

Interchange - Class that handles loading capnp schemas.

"""
import capnp
import capnp.lib.capnp
capnp.remove_import_hook()
import enum
import gzip
import os.path
from .logical_netlist import check_logical_netlist

# Flag indicating use of Packed Cap'n Proto Serialization
IS_PACKED = False


class CompressionFormat(enum.Enum):
    UNCOMPRESSED = 0
    GZIP = 1


# Flag indicating that files are gziped on output
DEFAULT_COMPRESSION_TYPE = CompressionFormat.GZIP


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
        f_in = gzip.GzipFile(fileobj=f_in, mode='rb')
    else:
        assert compression_format == CompressionFormat.UNCOMPRESSED

    if is_packed:
        return capnp_schema.read_packed(f_in)
    else:
        return capnp_schema.read(f_in)


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
        with gzip.GzipFile(fileobj=f_out, mode='wb') as f:
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

    """

    def __init__(self, logical_netlist_schema, name, cell_count, port_count,
                 cell_instance_count, property_map):
        self.logical_netlist_schema = logical_netlist_schema
        self.logical_netlist = self.logical_netlist_schema.Netlist.new_message(
        )

        self.logical_netlist.name = name

        self.string_map = {}
        self.string_list = []

        self.cell_idx = 0
        self.cell_count = cell_count
        self.logical_netlist.init("cellList", cell_count)
        self.cells = self.logical_netlist.cellList

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
        cell = self.cells[self.cell_idx]
        cell_idx = self.cell_idx
        self.cell_idx += 1

        return cell_idx, cell

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
                           top_level_cell,
                           top_level_name,
                           view="netlist",
                           property_map={}):
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
    assert top_level_cell in master_cell_list

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
        name=top_level_name,
        cell_count=cell_count,
        port_count=port_count,
        cell_instance_count=cell_instance_count,
        property_map=property_map)

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
            cell_idx, cell_obj = logical_netlist.next_cell()
            assert cell.name not in cell_name_to_idx
            cell_name_to_idx[cell.name] = cell_idx

            cell_obj.name = logical_netlist.string_id(cell.name)
            logical_netlist.create_property_map(cell_obj.propMap,
                                                cell.property_map)
            cell_obj.view = logical_netlist.string_id(cell.view)
            cell_obj.lib = library_id

            cell_obj.init('ports', len(cell.ports))
            for idx, (port_name, port) in enumerate(cell.ports.items()):
                port_idx, port_obj = logical_netlist.next_port()
                ports[cell.name, port_name] = (port_idx, port)
                cell_obj.ports[idx] = port_idx

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

    top_level_cell_instance = logical_netlist.get_top_cell_instance()

    # Convert the top level cell now that the libraries have been converted.
    top_level_cell_instance.name = logical_netlist.string_id(top_level_name)
    top_level_cell_instance.cell = cell_name_to_idx[top_level_cell]
    top_level_cell_instance.view = logical_netlist.string_id(view)
    logical_netlist.create_property_map(top_level_cell_instance.propMap,
                                        property_map)

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
        physical_netlist.part = phys_netlist.name
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

        physical_netlist.init('properties', len(self.properties))
        properties = physical_netlist.properties
        for idx, (k, v) in enumerate(self.properties.items()):
            properties[idx].key = self.string_id(k)
            properties[idx].value = self.string_id(v)

        physical_netlist.init('siteInsts', len(self.site_instances))
        site_instances = physical_netlist.siteInsts
        for idx, (k, v) in enumerate(self.site_instances.items()):
            site_instances[idx].site = self.string_id(k)
            site_instances[idx].type = self.string_id(v)

        physical_netlist.init('strList', len(self.string_list))

        for idx, s in enumerate(self.string_list):
            physical_netlist.strList[idx] = s

        return physical_netlist


def output_physical_netlist(physical_netlist_schema, physical_netlist):
    builder = PhysicalNetlistBuilder(physical_netlist_schema)
    return builder.encode(physical_netlist)


class Interchange():
    def __init__(self, schema_directory):

        search_path = [os.path.dirname(os.path.dirname(capnp.__file__))]
        if 'CONDA_PREFIX' in os.environ:
            search_path.append(
                os.path.join(os.environ['CONDA_PREFIX'], 'include'))

        for path in ['/usr/local/include', '/usr/include']:
            if os.path.exists(path):
                search_path.append(path)

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
        return read_capnp_file(self.logical_netlist_schema, f,
                               compression_format, is_packed)

    def read_physical_netlist_raw(self,
                              f,
                              compression_format=DEFAULT_COMPRESSION_TYPE,
                              is_packed=IS_PACKED):
        return read_capnp_file(self.physical_netlist_schema, f,
                               compression_format, is_packed)

    def read_device_resources_raw(
            self,
            f,
            compression_format=DEFAULT_COMPRESSION_TYPE,
            is_packed=IS_PACKED):
        return read_capnp_file(self.device_resources_schema, f,
                               compression_format, is_packed)
