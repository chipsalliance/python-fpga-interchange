import fpga_interchange
import fpga_interchange.interchange_capnp
from fpga_interchange.interchange_capnp import Interchange

from argparse import ArgumentParser
import yaml
import os

SCHEMA_PATH = os.environ.get('FPGA_INTERCHANGE_SCHEMA_PATH')

parser = ArgumentParser()
parser.add_argument('path', type=str)

args = parser.parse_args()

device = None
""" Access device resources through this variable """

interchange = Interchange(os.path.join(SCHEMA_PATH, 'interchange'))

device = None

path = args.path

with open(path, 'rb') as f:
    device = fpga_interchange.interchange_capnp.read_capnp_file(
        interchange.device_resources_schema.Device,
        f
    )

def string(idx):
    """ StringIdx -> str """
    return device.strList[idx]

def get_tile_type(name):
    """ Get `TileType` given a name """

    for tt in device.tileTypeList:
        if string(tt.name) == name:
            return tt
    return None

def get_site_type(name):
    """ Get `SiteType` given a name """

    for st in device.siteTypeList:
        if string(st.name) == name:
            return st
    return None

def cells_of_bel(site_type_name, bel_name):
    """
    Find all cells for a given site type and bel. The enumerator yields 
    two-element tuples, where the first one is a category ('common' or 'parameter')
    and the second  one is the name of the cell
    """

    for cb in device.cellBelMap:
        cell_name = string(cb.cell)
        ltc = [
            ('common', cb.commonPins, 'siteTypes'),
            ('parameter', cb.parameterPins, 'parametersSiteTypes')
        ]
        for cbpm_cat, cbpm_set, st_field in ltc:
            for cbpm in cbpm_set:
                for stbpm in getattr(cbpm, st_field):
                    if string(stbpm.siteType) != site_type_name:
                        continue
                    for bel in stbpm.bels:
                        stbpm_bel_name = string(bel)
                        if stbpm_bel_name == bel_name:
                            yield cbpm_cat, cell_name

def create_logical_netlist():
    """
    Get cell libraries associated with the device.
    """

    return fpga_interchange.interchange_capnp.to_logical_netlist(
        device.primLibs,
        [s for s in device.strList]
    )

def get_netlist_macros(netlist):
    """
    Get macro definitions from a cell library
    """

    m = {}
    for cell_name, cell in netlist.libraries['macros'].cells.items():
        m[cell_name] = {}
        for iname, instance in cell.cell_instances.items():
            m[cell_name][iname] = {
                'cell_name': instance.cell_name,
                'property_map': instance.property_map
            }
    return m

def name_of_pip(tt, pip):
    return f'{string(tt.wires[pip.wire0])}->{string(tt.wires[pip.wire1])}'

def site_pin_connections(site_type, bel_name, pin_name):
    for sw in site_type.siteWires:
        belpins = list(site_type.belPins[bp_idx] for bp_idx in sw.pins)
        bp_pairs = list((string(bp.bel), string(bp.name)) for bp in belpins)
        if (bel_name, pin_name) in bp_pairs:
            for conn in bp_pairs:
                yield conn

def pretty(*args, **kwargs):
    """
    Print YAML-formatted
    """

    print(yaml.dump(*args, **kwargs))

def lsp(l):
    """
    Print YAML-formatted, sorted
    """

    pretty(sorted(l))

def lsps(l):
    """
    Print YAML-formatted sorted list of strings
    """

    pretty(sorted(string(e) for e in l))
