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
""" This file uses the fpga_interchange to create a very simple FPGA design.

This design is target the 7-series FPGA line, and the physical netlist is
suitable for a Artix 50T class fabric.

To test this flow:

 - Invoke this script to output the logical netlist, physical netlist, and a
   small XDC file to set the IOSTANDARD's on the ports.
 - Use RapidWright's interchange branch to create a DCP using the entry point
   com.xilinx.rapidwright.interchange.PhysicalNetlistToDcp

   Example:

    export RAPIDWRIGHT_PATH=~/RapidWright
    $RAPIDWRIGHT_PATH/scripts/invoke_rapidwright.sh \
            com.xilinx.rapidwright.interchange.PhysicalNetlistToDcp \
            test.netlist test.phys test.xdc test.dcp

"""
import argparse

from fpga_interchange.interchange_capnp import Interchange, write_capnp_file
from fpga_interchange.logical_netlist import Library, Cell, Direction, CellInstance, LogicalNetlist
from fpga_interchange.physical_netlist import PhysicalNetlist, PhysicalBelPin, \
        Placement, PhysicalPip, PhysicalSitePin, PhysicalSitePip, \
        chain_branches, chain_pips, PhysicalNetType


def example_logical_netlist():
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
    top.add_cell_instance('clk_ibuf', 'IBUF')
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
    top.connect_net_to_instance('clk', 'clk_ibuf', 'I')

    top.add_net('clk_ibuf')
    top.connect_net_to_instance('clk_ibuf', 'clk_ibuf', 'O')
    top.connect_net_to_instance('clk_ibuf', 'clk_buf', 'I')

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

    return logical_netlist


def example_physical_netlist():
    phys_netlist = PhysicalNetlist(part='xc7a50tfgg484-1')

    ibuf_placement = Placement(
        cell_type='IBUF', cell_name='ibuf', site='IOB_X0Y12', bel='INBUF_EN')
    ibuf_placement.add_bel_pin_to_cell_pin(bel_pin='PAD', cell_pin='I')
    ibuf_placement.add_bel_pin_to_cell_pin(bel_pin='OUT', cell_pin='O')
    phys_netlist.add_placement(ibuf_placement)

    phys_netlist.add_site_instance(site_name='IOB_X0Y12', site_type='IOB33')

    obuf_placement = Placement(
        cell_type='OBUF', cell_name='obuf', site='IOB_X0Y11', bel='OUTBUF')
    obuf_placement.add_bel_pin_to_cell_pin(bel_pin='IN', cell_pin='I')
    obuf_placement.add_bel_pin_to_cell_pin(bel_pin='OUT', cell_pin='O')
    phys_netlist.add_placement(obuf_placement)

    phys_netlist.add_site_instance(site_name='IOB_X0Y11', site_type='IOB33')

    clk_ibuf_placement = Placement(
        cell_type='IBUF',
        cell_name='clk_ibuf',
        site='IOB_X0Y24',
        bel='INBUF_EN')
    clk_ibuf_placement.add_bel_pin_to_cell_pin(bel_pin='PAD', cell_pin='I')
    clk_ibuf_placement.add_bel_pin_to_cell_pin(bel_pin='OUT', cell_pin='O')
    phys_netlist.add_placement(clk_ibuf_placement)

    phys_netlist.add_site_instance(site_name='IOB_X0Y24', site_type='IOB33')

    clk_buf_placement = Placement(
        cell_type='BUFG',
        cell_name='clk_buf',
        site='BUFGCTRL_X0Y0',
        bel='BUFG')
    clk_buf_placement.add_bel_pin_to_cell_pin(bel_pin='I0', cell_pin='I')
    clk_buf_placement.add_bel_pin_to_cell_pin(bel_pin='O', cell_pin='O')
    phys_netlist.add_placement(clk_buf_placement)

    phys_netlist.add_site_instance(site_name='BUFGCTRL_X0Y0', site_type='BUFG')

    ff_placement = Placement(
        cell_type='FDRE', cell_name='ff', site='SLICE_X1Y12', bel='AFF')
    ff_placement.add_bel_pin_to_cell_pin(bel_pin='SR', cell_pin='R')
    ff_placement.add_bel_pin_to_cell_pin(bel_pin='D', cell_pin='D')
    ff_placement.add_bel_pin_to_cell_pin(bel_pin='Q', cell_pin='Q')
    ff_placement.add_bel_pin_to_cell_pin(bel_pin='CE', cell_pin='CE')
    ff_placement.add_bel_pin_to_cell_pin(bel_pin='CK', cell_pin='C')
    phys_netlist.add_placement(ff_placement)

    phys_netlist.add_site_instance(site_name='SLICE_X1Y12', site_type='SLICEL')

    i_root = chain_branches((PhysicalBelPin('IOB_X0Y12', 'PAD', 'PAD'),
                             PhysicalBelPin('IOB_X0Y12', 'INBUF_EN', 'PAD')))
    phys_netlist.add_physical_net(net_name='i', sources=[i_root], stubs=[])

    i_buf_root = chain_branches(
        (PhysicalBelPin('IOB_X0Y12', 'INBUF_EN', 'OUT'),
         PhysicalSitePip('IOB_X0Y12', 'IUSED', '0'),
         PhysicalBelPin('IOB_X0Y12', 'I', 'I'),
         PhysicalSitePin('IOB_X0Y12', 'I')) +
        chain_pips('LIOI3_X0Y11', ('LIOI_IBUF0', 'LIOI_I0', 'LIOI_ILOGIC0_D',
                                   'IOI_ILOGIC0_O', 'IOI_LOGIC_OUTS18_1')) +
        (PhysicalPip('IO_INT_INTERFACE_L_X0Y12',
                     'INT_INTERFACE_LOGIC_OUTS_L_B18',
                     'INT_INTERFACE_LOGIC_OUTS_L18'),
         PhysicalPip('INT_L_X0Y12', 'LOGIC_OUTS_L18', 'EE2BEG0'),
         PhysicalPip('INT_L_X2Y12', 'EE2END0', 'BYP_ALT0'),
         PhysicalPip('INT_L_X2Y12', 'BYP_ALT0', 'BYP_L0'),
         PhysicalPip('CLBLL_L_X2Y12', 'CLBLL_BYP0', 'CLBLL_L_AX'),
         PhysicalSitePin('SLICE_X1Y12', 'AX'),
         PhysicalBelPin('SLICE_X1Y12', 'AX', 'AX'),
         PhysicalSitePip('SLICE_X1Y12', 'AFFMUX', 'AX'),
         PhysicalBelPin('SLICE_X1Y12', 'AFF', 'D')))

    phys_netlist.add_physical_net(
        net_name='i_buf', sources=[i_buf_root], stubs=[])

    o_buf_root = chain_branches(
        (PhysicalBelPin('SLICE_X1Y12', 'AFF', 'Q'),
         PhysicalBelPin('SLICE_X1Y12', 'AQ', 'AQ'),
         PhysicalSitePin('SLICE_X1Y12', 'AQ'),
         PhysicalPip('CLBLL_L_X2Y12', 'CLBLL_L_AQ', 'CLBLL_LOGIC_OUTS0'),
         PhysicalPip('INT_L_X2Y12', 'LOGIC_OUTS_L0', 'SL1BEG0'),
         PhysicalPip('INT_L_X2Y11', 'SL1END0', 'WW2BEG0'),
         PhysicalPip('INT_L_X0Y11', 'WW2END0', 'IMUX_L34')) +
        chain_pips('LIOI3_X0Y11', ('IOI_IMUX34_0', 'IOI_OLOGIC1_D1',
                                   'LIOI_OLOGIC1_OQ', 'LIOI_O1')) +
        (
            PhysicalSitePin('IOB_X0Y11', 'O'),
            PhysicalBelPin('IOB_X0Y11', 'O', 'O'),
            PhysicalSitePip('IOB_X0Y11', 'OUSED', '0'),
            PhysicalBelPin('IOB_X0Y11', 'OUTBUF', 'IN'),
        ))
    phys_netlist.add_physical_net(
        net_name='o_buf', sources=[o_buf_root], stubs=[])

    o_root = chain_branches((PhysicalBelPin('IOB_X0Y11', 'OUTBUF', 'OUT'),
                             PhysicalBelPin('IOB_X0Y11', 'PAD', 'PAD')))
    phys_netlist.add_physical_net(net_name='o', sources=[o_root], stubs=[])

    clk_root = chain_branches((PhysicalBelPin('IOB_X0Y24', 'PAD', 'PAD'),
                               PhysicalBelPin('IOB_X0Y24', 'INBUF_EN', 'PAD')))
    phys_netlist.add_physical_net(net_name='clk', sources=[clk_root], stubs=[])

    clk_ibuf_root = chain_branches(
        (PhysicalBelPin('IOB_X0Y24', 'INBUF_EN', 'OUT'),
         PhysicalSitePip('IOB_X0Y24', 'IUSED', '0'),
         PhysicalBelPin('IOB_X0Y24', 'I', 'I'),
         PhysicalSitePin('IOB_X0Y24', 'I')) +
        chain_pips('LIOI3_X0Y23', ('LIOI_IBUF0', 'LIOI_I0', 'LIOI_ILOGIC0_D',
                                   'IOI_ILOGIC0_O', 'LIOI_I2GCLK_TOP0')) +
        (PhysicalPip('HCLK_CMT_X8Y26', 'HCLK_CMT_CCIO3',
                     'HCLK_CMT_MUX_CLK_13'),
         PhysicalPip('CLK_HROW_BOT_R_X60Y26', 'CLK_HROW_CK_IN_L13',
                     'CLK_HROW_BOT_R_CK_BUFG_CASCO0'),
         PhysicalPip('CLK_BUFG_BOT_R_X60Y48', 'CLK_BUFG_BOT_R_CK_MUXED0',
                     'CLK_BUFG_BUFGCTRL0_I0'),
         PhysicalSitePin('BUFGCTRL_X0Y0', 'I0'),
         PhysicalBelPin('BUFGCTRL_X0Y0', 'I0', 'I0'),
         PhysicalBelPin('BUFGCTRL_X0Y0', 'BUFG', 'I0')))
    phys_netlist.add_physical_net(
        net_name='clk_ibuf', sources=[clk_ibuf_root], stubs=[])

    clk_buf_root = chain_branches(
        (PhysicalBelPin('BUFGCTRL_X0Y0', 'BUFG', 'O'),
         PhysicalBelPin('BUFGCTRL_X0Y0', 'O', 'O'),
         PhysicalSitePin('BUFGCTRL_X0Y0', 'O'),
         PhysicalPip('CLK_BUFG_BOT_R_X60Y48', 'CLK_BUFG_BUFGCTRL0_O',
                     'CLK_BUFG_CK_GCLK0'),
         PhysicalPip(
             'CLK_BUFG_REBUF_X60Y38',
             'CLK_BUFG_REBUF_R_CK_GCLK0_TOP',
             'CLK_BUFG_REBUF_R_CK_GCLK0_BOT',
             forward=False)) + chain_pips('CLK_HROW_BOT_R_X60Y26', (
                 'CLK_HROW_R_CK_GCLK0', 'CLK_HROW_CK_MUX_OUT_L2',
                 'CLK_HROW_CK_HCLK_OUT_L2', 'CLK_HROW_CK_BUFHCLK_L2')) + (
                     PhysicalPip('HCLK_R_X12Y26', 'HCLK_CK_BUFHCLK2',
                                 'HCLK_LEAF_CLK_B_BOT4'),
                     PhysicalPip('INT_R_X3Y12', 'GCLK_B4', 'GCLK_B4_WEST'),
                     PhysicalPip('INT_L_X2Y12', 'GCLK_L_B4', 'CLK_L0'),
                     PhysicalPip('CLBLL_L_X2Y12', 'CLBLL_CLK0', 'CLBLL_L_CLK'),
                     PhysicalSitePin('SLICE_X1Y12', 'CLK'),
                     PhysicalBelPin('SLICE_X1Y12', 'CLK', 'CLK'),
                     PhysicalSitePip('SLICE_X1Y12', 'CLKINV', 'CLK'),
                     PhysicalBelPin('SLICE_X1Y12', 'AFF', 'CK'),
                 ))
    phys_netlist.add_physical_net(
        net_name='clk_buf', sources=[clk_buf_root], stubs=[])

    const0 = chain_branches((
        PhysicalBelPin('SLICE_X1Y12', 'SRUSEDGND', '0'),
        PhysicalSitePip('SLICE_X1Y12', 'SRUSEDMUX', '0'),
        PhysicalBelPin('SLICE_X1Y12', 'AFF', 'SR'),
    ))
    phys_netlist.add_physical_net(
        net_name='GLOBAL_LOGIC0',
        sources=[
            const0,
        ],
        stubs=[],
        net_type=PhysicalNetType.Gnd)

    const1 = chain_branches((
        PhysicalBelPin('SLICE_X1Y12', 'CEUSEDVCC', '1'),
        PhysicalSitePip('SLICE_X1Y12', 'CEUSEDMUX', '1'),
        PhysicalBelPin('SLICE_X1Y12', 'AFF', 'CE'),
    ))
    phys_netlist.add_physical_net(
        net_name='GLOBAL_LOGIC1',
        sources=[const1],
        stubs=[],
        net_type=PhysicalNetType.Vcc)

    return phys_netlist


def example_xdc():
    return """\
set_property IOSTANDARD LVCMOS33 [get_ports]
"""


def main():
    parser = argparse.ArgumentParser(
        description=
        "Create an example netlist, suitable for use with Vivado 2019.2")

    parser.add_argument('--schema_dir', required=True)
    parser.add_argument('--logical_netlist', required=True)
    parser.add_argument('--physical_netlist', required=True)
    parser.add_argument('--xdc', required=True)

    args = parser.parse_args()

    interchange = Interchange(args.schema_dir)
    logical_netlist = example_logical_netlist()
    logical_netlist_capnp = logical_netlist.convert_to_capnp(interchange)
    phys_netlist = example_physical_netlist()
    phys_netlist_capnp = phys_netlist.convert_to_capnp(interchange)

    with open(args.logical_netlist, 'wb') as f:
        write_capnp_file(logical_netlist_capnp, f)

    with open(args.physical_netlist, 'wb') as f:
        write_capnp_file(phys_netlist_capnp, f)

    with open(args.xdc, 'w') as f:
        f.write(example_xdc())


if __name__ == "__main__":
    main()
