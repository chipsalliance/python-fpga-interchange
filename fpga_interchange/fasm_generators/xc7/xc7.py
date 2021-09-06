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
"""
This file defines the Series-7 devices FASM generator class.

The FASM generator extends the generic one, with additional
functions and handlers for specific elements in the Series-7 devices.

The ultimate goal is to have most of the FASM annotations included in the
device resources, so that the size of this file can be reduced to handle
only very specific cases which are hard to encode in the device database.

Such special cases may include:
    - PLL and MMCM register configuration functions
    - Extra features corresponding to specific PIPs (such as BUFG rebuf)

"""
import re
import copy
from collections import namedtuple
from enum import Enum
from itertools import product

from fpga_interchange.fasm_generators.generic import FasmGenerator, \
                                                     PhysCellInstance, \
                                                     invert_bitstring
from fpga_interchange.fasm_generators import utils
from .xc7_iobs import iob_settings
from .xc7_cmt import compute_pll_lookup, compute_pll_clkregs
from .xc7_cmt import compute_mmcm_lookup, compute_mmcm_clkregs, \
                     compute_mmcm_clkregs_frac
from fpga_interchange.route_stitching import flatten_segments
from fpga_interchange.physical_netlist import PhysicalPip, Pin
from fpga_interchange.parameter_definitions import ParameterDefinition
from fpga_interchange.parameter_definitions import ParameterFormat
"""
This is a helper object that is used to find and emit extra features
that do depend on the usage of specific PIPs or Pseudo PIPs.

regex: is used to identify the correct PIPs.
features: list of extra features to be added.
callback: function to get the correct prefix for the feature, based on the
          regex match results.
"""
ExtraFeatures = namedtuple('ExtraFeatures', 'regex features callback')

VCC_NET = "GLOBAL_LOGIC1"
GND_NET = "GLOBAL_LOGIC0"


class LutsEnum(Enum):
    LUT5 = 0
    LUT6 = 1

    @classmethod
    def from_str(cls, label):
        if label == "LUT5":
            return cls.LUT5
        elif label == "LUT6":
            return cls.LUT6
        else:
            raise NotImplementedError


def parse_lut_bel(lut_bel):
    """
    Perform a regex match with the provided LUT name, to identify in which category
    the LUT falls into:

    input:
        lut_name = A5LUT

    output:
        lut_type = LUT5
        lut_loc  = A
    """

    bel_re = re.compile("([ABCD])([56])LUT")

    m = bel_re.match(lut_bel)
    assert m, lut_bel

    # A, B, C or D
    lut_loc = m.group(1)

    # LUT5 or LUT6
    lut_type = "LUT{}".format(m.group(2))

    return lut_loc, lut_type


class XC7FasmGenerator(FasmGenerator):
    @staticmethod
    def get_slice_prefix(site_name, tile_type):
        """
        Returns the slice prefix corresponding to the input site name.
        """

        slice_sites = {
            "CLBLL_L": ["SLICEL_X0", "SLICEL_X1"],
            "CLBLL_R": ["SLICEL_X0", "SLICEL_X1"],
            "CLBLM_L": ["SLICEM_X0", "SLICEL_X1"],
            "CLBLM_R": ["SLICEM_X0", "SLICEL_X1"],
        }

        slice_re = re.compile("SLICE_X([0-9]+)Y[0-9]+")
        m = slice_re.match(site_name)
        assert m, site_name

        slice_site_idx = int(m.group(1)) % 2
        return slice_sites[tile_type][slice_site_idx]

    @staticmethod
    def get_bram_prefix(site_name, tile_type):
        """
        Returns the bram prefix corresponding to the input site name.
        """

        ramb_re = re.compile("(RAMB(18|36))_X[0-9]+Y([0-9]+)")
        m = ramb_re.match(site_name)
        assert m, site_name

        ramb_site_idx = int(m.group(3)) % 2
        return "{}_Y{}".format(m.group(1), ramb_site_idx)

    @staticmethod
    def get_iologic_prefix(site_name, tile_type):
        """
        Returns the iologic prefix corresponding to the input site name.
        """

        iologic_re = re.compile("([IO](LOGIC|DELAY))_X[0-9]+Y([0-9]+)")
        m = iologic_re.match(site_name)
        assert m, site_name

        y_coord = int(m.group(3))
        if "SING" in tile_type and y_coord % 50 == 0:
            io_site_idx = 0
        elif "SING" in tile_type and y_coord % 50 == 49:
            io_site_idx = 1
        else:
            io_site_idx = y_coord % 2

        return "{}_Y{}".format(m.group(1), io_site_idx)

    def handle_brams(self):
        """
        Handles slice RAMB18 FASM feature emission.
        """

        init_re = re.compile("(INITP?_)([0-9A-F][0-9A-F])")

        z_features = ["INIT_A", "INIT_B", "SRVAL_A", "SRVAL_B"]
        str_features = [
            "RDADDR_COLLISION_HWCONFIG", "RSTREG_PRIORITY_A",
            "RSTREG_PRIORITY_B", "WRITE_MODE_A", "WRITE_MODE_B"
        ]
        rw_widths = [
            "READ_WIDTH_A", "READ_WIDTH_B", "WRITE_WIDTH_A", "WRITE_WIDTH_B"
        ]

        allowed_cell_types = ["RAMB18E1", "RAMB36E1"]
        allowed_site_types = ["RAMB18E1", "RAMB36E1"]

        for cell_instance, cell_data in self.physical_cells_instances.items():
            cell_type = cell_data.cell_type
            if cell_type not in allowed_cell_types:
                continue

            tile_name = cell_data.tile_name
            tile_type = cell_data.tile_type
            site_name = cell_data.site_name
            bram_prefix = self.get_bram_prefix(site_name, tile_type)

            if "RAMB18" in bram_prefix:
                is_y1 = "Y1" in bram_prefix

                self.add_cell_feature((tile_name, bram_prefix, "IN_USE"))

                attributes = cell_data.attributes

                fasm_features = list()
                ram_mode = attributes["RAM_MODE"]
                for attr, value in attributes.items():
                    init_param = self.device_resources.get_parameter_definition(
                        cell_type, attr)

                    init_match = init_re.match(attr)
                    fasm_feature = None
                    if init_match:
                        init_value = init_param.decode_integer(value)

                        if init_value == 0:
                            continue

                        init_str_value = "{:b}".format(init_value)
                        init_str = "{len}'b{value}".format(
                            len=len(init_str_value), value=init_str_value)
                        fasm_feature = "{}[{}:0]={}".format(
                            attr,
                            len(init_str_value) - 1, init_str)
                        fasm_features.append(fasm_feature)

                    elif attr in z_features:
                        init_value = init_param.decode_integer(value)
                        width = init_param.width

                        init_str_value = "{value:0{width}b}".format(
                            value=init_value, width=width)

                        feature_value = invert_bitstring(init_str_value)

                        fasm_feature = "Z{}[{}:0]={}'b{}".format(
                            attr, width - 1, width, feature_value)
                        fasm_features.append(fasm_feature)

                    elif attr in str_features:
                        fasm_features.append("{}_{}".format(attr, value))

                    elif attr in rw_widths:
                        init_value = init_param.decode_integer(value)

                        assert init_value == 36 and ram_mode == 'SDP' or init_value in [
                            0, 1, 2, 4, 9, 18
                        ], (init_value, ram_mode)

                        attr_prefix = attr[:-2]
                        if init_value == 36 and ram_mode == "SDP":
                            fasm_features.append("SDP_{}_36".format(attr[:-2]))
                            fasm_features = [
                                feature for feature in fasm_features
                                if not feature.startswith(attr_prefix)
                            ]
                            fasm_features.append("{}_{}".format(
                                attr_prefix + "_A",
                                18 if is_y1 or "WRITE" in attr_prefix else
                                1))  # Handle special INIT value case
                            fasm_features.append("{}_{}".format(
                                attr_prefix + "_B", 18))
                        else:
                            if init_value != 0 and not any([
                                    feature.startswith(attr)
                                    for feature in fasm_features
                            ]):
                                fasm_features.append("{}_{}".format(
                                    attr, init_value))

                for fasm_feature in fasm_features:
                    self.add_cell_feature((tile_name, bram_prefix,
                                           fasm_feature))

                if not is_y1:
                    for feature in [
                            "ALMOST_EMPTY_OFFSET", "ALMOST_FULL_OFFSET"
                    ]:
                        value = "1" * 13
                        fasm_feature = "Z{}[12:0]=13'b{}".format(
                            feature, value)
                        self.add_cell_feature((tile_name, fasm_feature))
            else:
                #TODO: add support for cascading
                brams = ["RAMB18_Y0", "RAMB18_Y1"]
                for bram in brams:
                    self.add_cell_feature((tile_name, bram, "IN_USE"))

                attributes = cell_data.attributes

                fasm_features = list()
                ram_mode = attributes["RAM_MODE"]

                init_types = ["INIT_{:02X}".format(i) for i in range(128)]
                init_name_dict = {
                    "INIT_{:02X}".format(i + 0x40): "INIT_{:02X}".format(i)
                    for i in range(64)
                }
                init_name_dict.update({
                    "INITP_{:02X}".format(i + 0x8): "INITP_{:02X}".format(i)
                    for i in range(8)
                })
                initp_types = ["INITP_{:02X}".format(i) for i in range(16)]

                init_dict = {}
                for value in init_types + initp_types:
                    init_dict[value] = 0

                for attr, value in attributes.items():
                    init_param = self.device_resources.get_parameter_definition(
                        cell_type, attr)

                    init_match = init_re.match(attr)
                    fasm_feature = None
                    if init_match:
                        init_pos = int(init_match.group(2), 16)
                        init_prefix = init_match.group(1)
                        init_value = init_param.decode_integer(value)

                        if init_value == 0:
                            continue

                        group = init_pos // 32
                        line = (init_pos - group * 32) // 2
                        bit_mask = 0
                        for i in range(0, 128):
                            bit_mask |= ((init_value & (1 << (i * 2))) >> i)
                        if init_pos % 2 == 1:
                            bit_mask <<= 128
                        init_dict[init_prefix + "{:X}".format(group) +
                                  "{:X}".format(line)] |= bit_mask
                        bit_mask = 0
                        for i in range(0, 128):
                            bit_mask |= ((init_value & (1 << (i * 2 + 1))) >>
                                         (i + 1))
                        if init_pos % 2 == 1:
                            bit_mask <<= 128
                        group += 4 if init_prefix == "INIT_" else 0
                        line += 0 if init_prefix == "INIT_" else 8
                        init_dict[init_prefix + "{:X}".format(group) +
                                  "{:X}".format(line)] |= bit_mask

                    elif attr in z_features:
                        init_value = init_param.decode_integer(value)
                        width = init_param.width

                        init_str_value = "{value:0{width}b}".format(
                            value=init_value, width=width)

                        feature_value = invert_bitstring(init_str_value)

                        for i, bram in enumerate(brams):
                            fasm_feature = "{}.Z{}[{}:0]={}'b{}".format(
                                bram, attr, width // 2 - 1, width // 2,
                                feature_value[18 * i:18 * (i + 1)])
                            fasm_features.append(fasm_feature)

                    elif attr in str_features:
                        for bram in brams:
                            fasm_features.append("{}.{}_{}".format(
                                bram, attr, value))

                    elif attr in rw_widths:
                        init_value = init_param.decode_integer(value)

                        assert init_value == 72 and ram_mode == 'SDP' or init_value in [
                            0, 1, 2, 4, 9, 18, 36
                        ], (init_value, ram_mode)

                        attr_prefix = attr[:-2]
                        if init_value == 72 and ram_mode == "SDP":
                            for bram in brams:
                                fasm_features.append("{}.SDP_{}_36".format(
                                    bram, attr[:-2]))
                                fasm_features = [
                                    feature for feature in fasm_features
                                    if not feature.startswith(attr_prefix)
                                ]
                                fasm_features.append("{}.{}_{}".format(
                                    bram, attr_prefix + "_A", 18))
                                fasm_features.append("{}.{}_{}".format(
                                    bram, attr_prefix + "_B", 18))
                        else:
                            if init_value % 2 == 1:
                                fasm_features.append(
                                    "RAMB36.BRAM36_{}_1".format(attr))
                                init_value = 2 if init_value == 1 else 8
                            init_value = init_value >> 1
                            for bram in brams:
                                if init_value != 0 and not any([
                                        feature.startswith(bram + "." + attr)
                                        for feature in fasm_features
                                ]):
                                    fasm_features.append("{}.{}_{}".format(
                                        bram, attr, init_value))

                for init, value in init_dict.items():
                    init_match = init_re.match(init)
                    init_pos = int(init_match.group(2), 16)
                    init_prefix = init_match.group(1)
                    init_str_value = "{:b}".format(value)
                    init_str = "{len}'b{value}".format(
                        len=len(init_str_value), value=init_str_value)
                    if init_prefix == "INIT_" and init_pos < 0x40 or init_prefix == "INITP_" and init_pos < 0x8:
                        self.add_cell_feature(
                            (tile_name, "RAMB18_Y0", "{}[{}:0]={}".format(
                                init,
                                len(init_str_value) - 1, init_str)))
                    else:
                        self.add_cell_feature(
                            (tile_name, "RAMB18_Y1", "{}[{}:0]={}".format(
                                init_name_dict[init],
                                len(init_str_value) - 1, init_str)))

                for fasm_feature in fasm_features:
                    self.add_cell_feature((tile_name, fasm_feature))

                for feature in [
                        "RAMB36.RAM_EXTENSION_A_NONE_OR_UPPER",
                        "RAMB36.RAM_EXTENSION_B_NONE_OR_UPPER"
                ]:
                    self.add_cell_feature((tile_name, feature))

                for feature in ["ALMOST_EMPTY_OFFSET", "ALMOST_FULL_OFFSET"]:
                    value = "1" * 13
                    fasm_feature = "Z{}[12:0]=13'b{}".format(feature, value)
                    self.add_cell_feature((tile_name, fasm_feature))

    def handle_ios(self):
        """
        This function is specialized to add FASM features for the IO buffers
        in the 7-Series database format.
        """

        # FIXME: Need to make this dynamic, and find a suitable way to add FASM annotations to the device resources.
        #        In addition, a reformat of the database might be required to have an easier handling of these
        #        features.
        allowed_io_types = [
            "IBUF", "OBUF", "OBUFT", "OBUFTDS", "OBUFDS", "IOBUFDS"
        ]

        iob_sites = ["IOB_Y0", "IOB_Y1"]
        iob_re = re.compile("IOB_X[0-9]+Y([0-9]+)")

        iob_instances = {}

        for cell_data in self.physical_cells_instances.values():
            cell_type = cell_data.cell_type
            if cell_type not in allowed_io_types:
                continue

            site_name = cell_data.site_name
            tile_name = cell_data.tile_name
            attrs = cell_data.attributes

            if site_name not in iob_instances:
                iob_instances[site_name] = (attrs, tile_name, False, False)

            attrs, tile_name, is_input, is_output = iob_instances[site_name]

            if cell_type.startswith("O"):
                is_output = True

            if cell_type.startswith("I"):
                is_input = True

            iob_instances[site_name] = (attrs, tile_name, is_input, is_output)

        for site_name, (attrs, tile_name, is_input,
                        is_output) in iob_instances.items():

            iostandard = attrs.get("IOSTANDARD", "LVCMOS33")
            drive = int(attrs.get("DRIVE", "12"))
            slew = attrs.get("SLEW", "SLOW")

            is_inout = is_input and is_output
            is_only_in = is_input and not is_output

            m = iob_re.match(site_name)
            assert m, site_name

            y_coord = int(m.group(1))
            if "SING" in tile_name and y_coord % 50 == 0:
                iob_sites_idx = 0
            elif "SING" in tile_name and y_coord % 50 == 49:
                iob_sites_idx = 1
            else:
                iob_sites_idx = y_coord % 2

            iob_site = iob_sites[iob_sites_idx]

            for feature, settings in iob_settings.items():
                if feature.endswith("IN_ONLY") and is_output:
                    continue

                if ("DRIVE" in feature or "SLEW" in feature) and is_only_in:
                    continue

                if (feature.endswith("IN")
                        or feature.endswith("IN_DIFF")) and not is_input:
                    continue

                iostandards = settings["iostandards"]
                slews = settings["slews"]

                if len(iostandards) != 0 and iostandard not in iostandards:
                    continue

                drives = iostandards[iostandard]
                if len(drives) != 0 and drive not in drives:
                    continue

                if len(slews) != 0 and slew not in slews:
                    continue

                self.add_cell_feature((tile_name, iob_site, feature))

            pulltype = attrs.get("PULLTYPE", "NONE")
            self.add_cell_feature((tile_name, iob_site, "PULLTYPE", pulltype))

            if iostandard.startswith("DIFF_") and is_output:
                self.add_cell_feature((tile_name, "OUT_DIFF"))

    def handle_iologic(self):
        """
        Handles the IOLOGIC tiles, includeing ISERDES, OSERDES, IDELAY
        """

        cell_features = set()

        def handle_iserdes(cell_data):
            tile_name = cell_data.tile_name
            tile_type = cell_data.tile_type
            site_name = cell_data.site_name
            cell_type = cell_data.cell_type
            prefix = self.get_iologic_prefix(site_name, tile_type)

            attrs = cell_data.attributes

            itype = attrs.get("INTERFACE_TYPE", "MEMORY")
            width = "W{}".format(attrs.get("DATA_WIDTH", "4"))
            data_rate = attrs.get("DATA_RATE", "DDR")
            feature = ".".join([itype, data_rate, width])

            cell_features.add((tile_name, prefix, "ISERDES", feature))

            num_ce = attrs.get("NUM_CE", "2")
            cell_features.add((tile_name, prefix,
                               "ISERDES.NUM_CE.N{}".format(num_ce)))

            iob_delay = attrs.get("IOBDELAY", "NONE")

            for idelay in ["IFD", "IBUF"]:
                if iob_delay in [idelay, "BOTH"]:
                    cell_features.add((tile_name, prefix,
                                       "IOBDELAY_{}".format(idelay)))

            for z_feature in ["INIT", "SRVAL"]:
                for q in range(1, 5):
                    z_attr = "{}_Q{}".format(z_feature, q)
                    z_value = attrs.get(z_attr, 0)
                    z_param = self.device_resources.get_parameter_definition(
                        cell_type, z_attr)

                    z_value = z_param.decode_integer(z_value)

                    if z_value == 0:
                        cell_features.add((tile_name, prefix,
                                           "IFF.Z{}_Q{}".format(z_feature, q)))

        def handle_oserdes(cell_data):
            tile_name = cell_data.tile_name
            tile_type = cell_data.tile_type
            site_name = cell_data.site_name
            cell_type = cell_data.cell_type
            prefix = self.get_iologic_prefix(site_name, tile_type)

            attrs = cell_data.attributes

            common_feature = ".".join((tile_name, prefix, "OSERDES"))

            # Always present feature
            cell_features.add((common_feature, "IN_USE"))
            cell_features.add((common_feature, "SRTYPE.SYNC"))
            cell_features.add((common_feature, "TSRTYPE.SYNC"))
            cell_features.add((tile_name, prefix,
                               "ODDR.DDR_CLK_EDGE.SAME_EDGE"))
            cell_features.add((tile_name, prefix, "ODDR.SRUSED"))
            cell_features.add((tile_name, prefix, "OQUSED"))

            data_width = "W{}".format(attrs.get("DATA_WIDTH", "4"))
            features = {
                "DATA_RATE_OQ": "DDR",
                "DATA_RATE_TQ": "DDR",
                "SERDES_MODE": "MASTER"
            }
            for k, v in features.items():
                attr = attrs.get(k, v)

                if v != "MASTER":
                    cell_features.add((common_feature, k, attr))

                if k == "DATA_RATE_OQ":
                    cell_features.add((common_feature, "DATA_WIDTH", attr,
                                       data_width))

            tristate_width = attrs.get("TRISTATE_WIDTH", "4")
            if tristate_width == "4":
                cell_features.add((common_feature, "TRISTATE_WIDTH",
                                   "W{}".format(tristate_width)))

            for z_attr in ["INIT_TQ", "INIT_OQ", "SRVAL_TQ", "SRVAL_OQ"]:
                z_value = attrs.get(z_attr, 0)
                z_param = self.device_resources.get_parameter_definition(
                    cell_type, z_attr)

                z_value = z_param.decode_integer(z_value)

                if z_value == 0:
                    cell_features.add((tile_name, prefix,
                                       "Z{}".format(z_attr)))

        def handle_idelay(cell_data):
            tile_name = cell_data.tile_name
            tile_type = cell_data.tile_type
            site_name = cell_data.site_name
            cell_type = cell_data.cell_type
            prefix = self.get_iologic_prefix(site_name, tile_type)

            attrs = cell_data.attributes

            cell_features.add((tile_name, prefix, "IN_USE"))
            features = {
                "DELAY_SRC": "IDATAIN",
                "IDELAY_TYPE": "FIXED",
                "HIGH_PERFORMANCE_MODE": "FALSE",
                "CINVCTRL_SEL": "FALSE",
                "PIPE_SEL": "FALSE"
            }

            for k, v in features.items():
                v = attrs.get(k, v)
                if v == "FALSE":
                    continue
                elif v == "TRUE":
                    cell_features.add((tile_name, prefix, k))
                else:
                    cell_features.add((tile_name, prefix, "{}_{}".format(k,
                                                                         v)))

            delay_value = attrs.get("IDELAY_VALUE", "1'b0")
            delay_param = self.device_resources.get_parameter_definition(
                cell_type, "IDELAY_VALUE")

            delay_value = delay_param.decode_integer(delay_value)

            delay_str_value = "{:b}".format(delay_value)
            delay_str = "{len}'b{value}".format(
                len=len(delay_str_value), value=delay_str_value)
            delay_feature = "{}[{}:0]={}".format("IDELAY_VALUE",
                                                 len(delay_str_value) - 1,
                                                 delay_str)

            zdelay_str_value = invert_bitstring(delay_str_value)
            zdelay_str = "{len}'b{value}".format(
                len=len(zdelay_str_value), value=zdelay_str_value)
            zdelay_feature = "{}[{}:0]={}".format("ZIDELAY_VALUE",
                                                  len(zdelay_str_value) - 1,
                                                  zdelay_str)

            cell_features.add((tile_name, prefix, delay_feature))
            cell_features.add((tile_name, prefix, zdelay_feature))

        ioi_handlers = {
            "ISERDESE2": handle_iserdes,
            "OSERDESE2": handle_oserdes,
            "IDELAYE2": handle_idelay,
        }

        for cell_data in self.physical_cells_instances.values():
            cell_type = cell_data.cell_type
            if cell_type not in ioi_handlers:
                continue

            ioi_handlers[cell_type](cell_data)

        for feature in cell_features:
            self.add_cell_feature(feature)

    def add_lut_features(self):
        for lut in self.luts.values():
            tile_name, slice_site, lut_name = lut["data"]

            lut5 = lut[LutsEnum.LUT5]
            lut6 = lut[LutsEnum.LUT6]

            if lut5 is not None and lut6 is not None:
                lut_init = "{}{}".format(lut6[0:32], lut5[32:64])
            elif lut5 is not None:
                lut_init = lut5[32:64].zfill(32)
            elif lut6 is not None:
                lut_init = lut6
            else:
                assert False

            init_feature = "INIT[{}:0]={}'b{}".format(
                len(lut_init) - 1, len(lut_init), lut_init)

            self.add_cell_feature((tile_name, slice_site, lut_name,
                                   init_feature))

    def handle_luts(self):
        """
        This function handles LUTs FASM features generation
        """

        self.luts = dict()

        for cell_instance, cell_data in self.physical_cells_instances.items():
            if not cell_data.cell_type.startswith("LUT"):
                continue

            site_name = cell_data.site_name
            site_type = cell_data.site_type

            tile_name = cell_data.tile_name
            tile_type = cell_data.tile_type
            slice_site = self.get_slice_prefix(site_name, tile_type)

            bel = cell_data.bel
            lut_loc, lut_type = parse_lut_bel(bel)
            lut_name = "{}LUT".format(lut_loc)

            init_param = self.device_resources.get_parameter_definition(
                cell_data.cell_type, "INIT")
            init_value = init_param.decode_integer(
                cell_data.attributes["INIT"])

            phys_lut_init = self.lut_mapper.get_phys_cell_lut_init(
                init_value, cell_data)

            key = (site_name, lut_loc)
            if key not in self.luts:
                self.luts[key] = {
                    "data": (tile_name, slice_site, lut_name),
                    LutsEnum.LUT5: None,
                    LutsEnum.LUT6: None,
                }

            self.luts[key][LutsEnum.from_str(lut_type)] = phys_lut_init

    def handle_slice_ff(self):
        """
        Handles slice FFs FASM feature emission.
        """

        allowed_cell_types = ["FDRE", "FDSE", "FDCE", "FDPE", "LDCE", "LDPE"]
        allowed_site_types = ["SLICEL", "SLICEM"]

        for cell_instance, cell_data in self.physical_cells_instances.items():
            cell_type = cell_data.cell_type
            if cell_type not in allowed_cell_types:
                continue

            site_name = cell_data.site_name
            site_type = cell_data.site_type

            if site_type not in allowed_site_types:
                continue

            tile_name = cell_data.tile_name
            tile_type = cell_data.tile_type
            slice_site = self.get_slice_prefix(site_name, tile_type)

            bel = cell_data.bel

            if cell_type in ["FDRE", "FDCE", "LDCE"]:
                self.add_cell_feature((tile_name, slice_site, bel, "ZRST"))

            if cell_type.startswith("LD"):
                self.add_cell_feature((tile_name, slice_site, "LATCH"))

            if cell_type in ["FDRE", "FDSE"]:
                self.add_cell_feature((tile_name, slice_site, "FFSYNC"))

            init_param = self.device_resources.get_parameter_definition(
                cell_data.cell_type, "INIT")
            init_value = init_param.decode_integer(
                cell_data.attributes["INIT"])

            if init_value == 0:
                self.add_cell_feature((tile_name, slice_site, bel, "ZINI"))

    @staticmethod
    def yield_pll_mmcm_clkregs_features(name, clkregs):
        """
        Yields strings with feature names and their assigned values that
        correspond to parts or PLL/MMCM clock registers
        """

        # DIVCLK have different feature names
        if name == "DIVCLK":
            pfx1 = "DIVCLK"
            pfx2 = "DIVCLK"
        else:
            pfx1 = "CLKOUT1"
            pfx2 = "CLKOUT2"

        yield "{}_{}_HIGH_TIME{}".format(
            name, pfx1, utils.format_feature_value(clkregs[6:12]))
        yield "{}_{}_LOW_TIME{}".format(
            name, pfx1, utils.format_feature_value(clkregs[0:6]))

        # A corner case for DIVCLK
        if name != "DIVCLK":
            yield "{}_{}_PHASE_MUX{}".format(
                name, pfx1, utils.format_feature_value(clkregs[13:16]))
            yield "{}_{}_DELAY_TIME{}".format(
                name, pfx2, utils.format_feature_value(clkregs[16:22]))

        yield "{}_{}_EDGE{}".format(name, pfx2,
                                    utils.format_feature_value(clkregs[23]))
        yield "{}_{}_NO_COUNT{}".format(
            name, pfx2, utils.format_feature_value(clkregs[22]))

    @staticmethod
    def yield_mmcm_clkregs_frac_features(name, clkregs):
        """
        Yields strings with feature names and their assigned values that
        correspond to parts or clock registers that have fractional divider
        which are CLKFBOUT and CLKOUT0
        """

        yield "{}_CLKOUT2_FRAC{}".format(
            name, utils.format_feature_value(clkregs[28:31]))
        yield "{}_CLKOUT2_FRAC_EN{}".format(
            name, utils.format_feature_value(clkregs[27]))
        yield "{}_CLKOUT2_FRAC_WF_R{}".format(
            name, utils.format_feature_value(clkregs[26]))

    @staticmethod
    def yield_mmcm_clkregs_features(name, clkregs):
        """
        Yields strings with feature names and their assigned values for
        CLKOUT5 and CLKOUT6 of MMCM which have some features shared with
        others and named differently
        """

        yield "{}_CLKOUT1_HIGH_TIME{}".format(
            name, utils.format_feature_value(clkregs[6:12]))
        yield "{}_CLKOUT1_LOW_TIME{}".format(
            name, utils.format_feature_value(clkregs[0:6]))
        yield "{}_CLKOUT1_PHASE_MUX{}".format(
            name, utils.format_feature_value(clkregs[13:16]))

        yield "{}_CLKOUT2_FRACTIONAL_DELAY_TIME{}".format(
            name, utils.format_feature_value(clkregs[16:22]))
        yield "{}_CLKOUT2_FRACTIONAL_EDGE{}".format(
            name, utils.format_feature_value(clkregs[23]))
        yield "{}_CLKOUT2_FRACTIONAL_NO_COUNT{}".format(
            name, utils.format_feature_value(clkregs[22]))
        yield "{}_CLKOUT2_FRACTIONAL_PHASE_MUX_F{}".format(
            name, utils.format_feature_value(clkregs[27:30]))
        yield "{}_CLKOUT2_FRACTIONAL_FRAC_WF_F{}".format(
            name, utils.format_feature_value(clkregs[26]))

    def handle_pll_mmcm_common(self, cell_data):
        """
        Handles FASM feature emission common to PLLE2_ADV and MMCME2_ADV
        """

        tile_name = cell_data.tile_name
        bel = cell_data.bel

        # Get BEL pin assignments
        bel_pins = self.get_bel_pins_annotation(tile_name, bel)

        # IN_USE
        self.add_cell_feature((tile_name, bel, "IN_USE"))

        # Boolean parameters
        val = utils.get_cell_integer_param(self.device_resources, cell_data,
                                           "STARTUP_WAIT",
                                           ParameterFormat.BOOLEAN)
        if val:
            self.add_cell_feature((tile_name, bel, "STARTUP_WAIT"))

        # Clock output enables
        for clkname in [
                "CLKFBOUT", "CLKOUT0", "CLKOUT1", "CLKOUT2", "CLKOUT3",
                "CLKOUT4", "CLKOUT5"
        ]:
            feature = "{}_CLKOUT1_OUTPUT_ENABLE".format(clkname)
            if clkname in bel_pins:
                self.add_cell_feature((tile_name, bel, feature))

    def handle_pll(self, cell_data):
        """
        Handles emission of PLLE2_ADV features
        """

        # Common features
        self.handle_pll_mmcm_common(cell_data)

        tile_name = cell_data.tile_name
        bel = cell_data.bel

        # FIXME: Is this one supposed to be emitted always ?
        self.add_cell_feature((tile_name, bel,
                               "COMPENSATION.Z_ZHOLD_OR_CLKIN_BUF"))

        # Lookup tables
        clkfbout_mult = utils.get_cell_integer_param(
            self.device_resources, cell_data, "CLKFBOUT_MULT")
        bandwidth = cell_data.attributes["BANDWIDTH"].lower()

        lktable, table = compute_pll_lookup(clkfbout_mult, bandwidth)

        self.add_cell_feature((tile_name, bel,
                               "LKTABLE[39:0]={}".format(lktable)))
        self.add_cell_feature((tile_name, bel, "TABLE[9:0]={}".format(table)))

        # Fixed parameters
        self.add_cell_feature((tile_name, bel,
                               "FILTREG1_RESERVED[11:0]=12'b000000001000"))
        self.add_cell_feature((tile_name, bel, "LOCKREG3_RESERVED[0]=1'b1"))

        # Multipliers / dividers
        for clkname in [
                "CLKFBOUT", "DIVCLK", "CLKOUT0", "CLKOUT1", "CLKOUT2",
                "CLKOUT3", "CLKOUT4", "CLKOUT5"
        ]:

            if clkname == "CLKFBOUT":
                param = "CLKFBOUT_MULT"
            else:
                param = "{}_DIVIDE".format(clkname)
            muldiv = utils.get_cell_integer_param(self.device_resources,
                                                  cell_data, param)

            if clkname in ["CLKFBOUT", "DIVCLK"]:
                duty = 0.5
            else:
                param = "{}_DUTY_CYCLE".format(clkname)
                duty = float(cell_data.attributes[param])

            if clkname == "CLKFBOUT":
                phase = float(cell_data.attributes["CLKFBOUT_PHASE"])
            elif clkname == "DIVCLK":
                phase = 0.0
            else:
                param = "{}_PHASE".format(clkname)
                phase = float(cell_data.attributes[param])

            clkregs = compute_pll_clkregs(muldiv, duty, phase)
            for f in self.yield_pll_mmcm_clkregs_features(clkname, clkregs):
                self.add_cell_feature((tile_name, bel, f))

    def handle_mmcm(self, cell_data):
        """
        Handles emission of MMCME2_ADV features
        """

        # Common features
        self.handle_pll_mmcm_common(cell_data)

        tile_name = cell_data.tile_name
        bel = cell_data.bel

        # Get BEL pin assignments
        bel_pins = self.get_bel_pins_annotation(tile_name, bel)

        # Boolean parameters
        ss_en = utils.get_cell_integer_param(self.device_resources, cell_data,
                                             "SS_EN", ParameterFormat.BOOLEAN)
        if ss_en:
            self.add_cell_feature((tile_name, bel, "SS_EN"))

        # CLKOUT6 output enable
        if "CLKOUT6" in bel_pins:
            self.add_cell_feature((tile_name, bel,
                                   "CLKOUT6_CLKOUT1_OUTPUT_ENABLE"))

        # Lookup tables
        clkfbout_mult = int(float(cell_data.attributes["CLKFBOUT_MULT_F"]))
        bandwidth = cell_data.attributes["BANDWIDTH"].lower()

        lktable, table = compute_mmcm_lookup(
            int(clkfbout_mult), bandwidth, ss_en)

        self.add_cell_feature((tile_name, bel,
                               "LKTABLE[39:0]={}".format(lktable)))
        self.add_cell_feature((tile_name, bel, "TABLE[9:0]={}".format(table)))

        # Fixed parameters
        self.add_cell_feature((tile_name, bel,
                               "FILTREG1_RESERVED[11:0]=12'b000000001000"))
        self.add_cell_feature((tile_name, bel, "LOCKREG3_RESERVED[0]=1'b1"))

        # Compensation
        compensation = cell_data.attributes["COMPENSATION"]
        if compensation == "ZHOLD":
            self.add_cell_feature((tile_name, bel, "COMP.ZHOLD"))
        else:
            self.add_cell_feature((tile_name, bel, "COMP.Z_ZHOLD"))

        # Round fractional dividers to the nearest multiple of 0.125
        clkfbout_mult = float(cell_data.attributes["CLKFBOUT_MULT_F"])
        clkout0_divide = float(cell_data.attributes["CLKOUT0_DIVIDE_F"])

        clkfbout_mult_r = int((clkfbout_mult + 0.0625) / 0.125) * 0.125
        clkout0_divide_r = int((clkout0_divide + 0.0625) / 0.125) * 0.125

        # Determine whether fractional dividers are enabled
        clkfbout_frac_en = \
            abs(int(clkfbout_mult_r) - clkfbout_mult_r) > 0.0625
        clkout0_frac_en = \
            abs(int(clkout0_divide_r) - clkout0_divide_r) > 0.0625

        # Determine if phase shift of CLKFBOUT and CLKOUT0 is a multiple of
        # 45 degrees
        clkfbout_phase = float(cell_data.attributes["CLKFBOUT_PHASE"])
        clkout0_phase = float(cell_data.attributes["CLKOUT0_PHASE"])

        clkfbout_phase_45 = (int(clkfbout_phase) % 45) == 0
        clkout0_phase_45 = (int(clkout0_phase) % 45) == 0

        # Power register
        if clkfbout_frac_en or clkout0_frac_en or not clkout0_phase_45:
            power_reg = "16'b1001100100000000"
        else:
            power_reg = "16'b0000000100000000"
        self.add_cell_feature(
            (tile_name, bel,
             "POWER_REG_POWER_REG_POWER_REG[15:0]=" + power_reg))

        # "Regular" multipliers / dividers
        for clkname in ["DIVCLK", "CLKOUT1", "CLKOUT2", "CLKOUT3", "CLKOUT4"]:

            param = "{}_DIVIDE".format(clkname)
            muldiv = utils.get_cell_integer_param(self.device_resources,
                                                  cell_data, param)

            if clkname == "DIVCLK":
                duty = 0.5
            else:
                param = "{}_DUTY_CYCLE".format(clkname)
                duty = float(cell_data.attributes[param])

            if clkname == "DIVCLK":
                phase = 0.0
            else:
                param = "{}_PHASE".format(clkname)
                phase = float(cell_data.attributes[param])

            clkregs = compute_mmcm_clkregs(muldiv, duty, phase)
            for f in self.yield_pll_mmcm_clkregs_features(clkname, clkregs):
                self.add_cell_feature((tile_name, bel, f))

        # Fractional multipliers / dividers + "regualr" ones that share their
        # registers with them
        for clkname1, clkname2 in [("CLKFBOUT", "CLKOUT6"), \
                                   ("CLKOUT0", "CLKOUT5")]:

            # Compute registers for the "other" clock (integer only). Will be
            # used later
            param = "{}_DIVIDE".format(clkname2)
            muldiv = utils.get_cell_integer_param(self.device_resources,
                                                  cell_data, param)

            param = "{}_DUTY_CYCLE".format(clkname2)
            duty = float(cell_data.attributes[param])

            param = "{}_PHASE".format(clkname2)
            phase = float(cell_data.attributes[param])

            clkregs2 = compute_mmcm_clkregs(muldiv, duty, phase)

            # Compute registers for integer divider of the first clock
            if clkname1 == "CLKFBOUT":
                muldiv = clkfbout_mult_r
                frac_en = clkfbout_frac_en
            if clkname1 == "CLKOUT0":
                muldiv = clkout0_divide_r
                frac_en = clkout0_frac_en

            if clkname1 == "CLKFBOUT" or frac_en:
                duty = 0.5
            else:
                param = "{}_DUTY_CYCLE".format(clkname1)
                duty = float(cell_data.attributes[param])

            param = "{}_PHASE".format(clkname1)
            phase = float(cell_data.attributes[param])

            clkregs1 = compute_mmcm_clkregs(int(muldiv), duty, phase)

            # Fractional divider enabled
            if frac_en:

                clkregs1_frac = compute_mmcm_clkregs_frac(muldiv, 0.5, phase)

                # When no fractional divider is enabled use the *_regs content.
                # For fractional divider use *_regs_frac content but take the
                # "EDGE" bit from *_regs. This is not documented in XAPP888 but
                # has been observed in vendor tools.
                clkregs1 = clkregs1_frac[:23] + \
                           clkregs1[23] + \
                           clkregs1_frac[24:32]

                # Integrate shared part of clkregs1 with clkregs2
                clkregs2 = clkregs2[:26] + \
                           clkregs1_frac[32:36] + \
                           clkregs2[30:32]

            # Fractional divider disabled
            else:

                # Integrate shared part of clkregs1 with clkregs2
                clkregs2 = clkregs2[:27] + \
                           clkregs1[13:16] + \
                           clkregs2[30:32]

            # For CLKFBOUT and CLKOUT0
            for f in self.yield_pll_mmcm_clkregs_features(clkname1, clkregs1):
                self.add_cell_feature((tile_name, bel, f))

            for f in self.yield_mmcm_clkregs_frac_features(clkname1, clkregs1):
                self.add_cell_feature((tile_name, bel, f))

            # For CLKOUT5 and CLKOUT6
            for f in self.yield_mmcm_clkregs_features(clkname2, clkregs2):
                self.add_cell_feature((tile_name, bel, f))

    def handle_cmts(self):
        """
        Handles FASM features for CMT tiles
        """
        for cell_instance, cell_data in self.physical_cells_instances.items():

            if cell_data.cell_type == "PLLE2_ADV":
                self.handle_pll(cell_data)

            elif cell_data.cell_type == "MMCME2_ADV":
                self.handle_mmcm(cell_data)

    def handle_clock_resources(self):

        bufg_re = re.compile("BUFGCTRL_X[0-9]+Y([0-9]+)")
        for cell_instance, cell_data in self.physical_cells_instances.items():
            cell_type = cell_data.cell_type
            if cell_type not in ["BUFG", "BUFGCTRL"]:
                continue

            site_name = cell_data.site_name
            site_type = cell_data.site_type

            m = bufg_re.match(cell_data.site_name)
            assert m, site_name

            site_loc = int(m.group(1)) % 16
            site_prefix = "BUFGCTRL.BUFGCTRL_X0Y{}".format(site_loc)

            tile_name = cell_data.tile_name

            self.add_cell_feature((tile_name, site_prefix, "IN_USE"))

            if cell_type == "BUFG":
                for feature in ["IS_IGNORE1_INVERTED", "ZINV_CE0", "ZINV_S0"]:
                    self.add_cell_feature((tile_name, site_prefix, feature))

    def handle_slice_routing_bels(self):
        tile_types = ["CLBLL_L", "CLBLL_R", "CLBLM_L", "CLBLM_R"]
        routing_bels = self.get_routing_bels(tile_types)

        used_muxes = ["SRUSEDMUX", "CEUSEDMUX"]

        excluded_bels = [
            "{}USED".format(bel) for bel in ["A", "B", "C", "D", "COUT"]
        ]
        excluded_bels += ["CLKINV"]

        carry_cy = ["{}CY0".format(bel) for bel in ["A", "B", "C", "D"]]
        slicem_srl_mux = {
            "CDI1MUX": {
                "LUT": "CLUT",
                "DI": "DI_DMC31",
                "DMC31": "DI_DMC31",
                "CI": "CI"
            },
            "BDI1MUX": {
                "LUT": "BLUT",
                "DI": "DI_CMC31",
                "CMC31": "DI_CMC31",
                "BI": "BI"
            },
            "ADI1MUX": {
                "LUT": "ALUT",
                "BDI1": "BDI1_BMC31",
                "BMC31": "BDI1_BMC31",
                "AI": "AI"
            },
        }

        for site, bel, pin, _ in routing_bels:
            if bel in excluded_bels:
                continue

            tile_name, tile_type = self.get_tile_info_at_site(site)
            slice_prefix = self.get_slice_prefix(site, tile_type)

            if bel in used_muxes:
                if pin in ["0", "1"]:
                    continue
                feature = (tile_name, slice_prefix, bel)
            elif bel in carry_cy:
                # TODO: requires possible adjustment to the FASM database format
                if pin != "O5":
                    continue
                feature = (tile_name, slice_prefix, "CARRY4", bel)
            elif bel == "PRECYINIT":
                if pin == "1":
                    # TODO: requires possible adjustment to the FASM database format
                    pin = "C{}".format(pin)
                elif pin == "0":
                    # default value, do not emit as might collide with CIN
                    continue
                feature = (tile_name, slice_prefix, bel, pin)
            elif bel in slicem_srl_mux.keys():
                feature = (tile_name, slice_prefix, slicem_srl_mux[bel]['LUT'],
                           "DI1MUX", slicem_srl_mux[bel][pin])
            elif bel == "WEMUX":
                if pin == "CE":
                    feature = (tile_name, slice_prefix, bel, pin)
                else:
                    continue
            else:
                feature = (tile_name, slice_prefix, bel, pin)

            self.add_cell_feature(feature)

    def handle_bram_routing_bels(self):
        tile_types = ["BRAM_L", "BRAM_R"]
        routing_bels = self.get_routing_bels(tile_types)

        for site, bel, pin, is_inverting in routing_bels:
            tile_name, tile_type = self.get_tile_info_at_site(site)
            bram_prefix = self.get_bram_prefix(site, tile_type)

            if "RAMB18" in bram_prefix:
                if not is_inverting:
                    zinv_feature = "ZINV_{}".format(pin)
                    self.add_cell_feature((tile_name, bram_prefix,
                                           zinv_feature))
            elif "RAMB36" in bram_prefix:
                if not is_inverting:
                    zinv_feature = "{}.ZINV_{}".format(
                        "RAMB18_Y0" if pin[-1] == "L" else "RAMB18_Y1",
                        pin[:-1])
                    self.add_cell_feature((tile_name, zinv_feature))

    def handle_ioi_routing_bels(self):
        tile_types = [
            "LIOI3", "LIOI3_SING", "LIOI3_TBYTETERM", "LIOI3_TBYTESRC",
            "RIOI3", "RIOI3_SING", "RIOI3_TBYTETERM", "RIOI3_TBYTESRC"
        ]
        routing_bels = self.get_routing_bels(tile_types)

        zinv_pins = {
            "OLOGIC": {
                "CLK": "CLK",
            },
            "IDELAY": {},
            "ILOGIC": {
                "CLK": "C"
            },
        }

        inverting_pins = ["D{}_B".format(i) for i in range(1, 9)]
        inverting_pins += ["DATAIN_B", "IDATAIN_B"]

        for site, bel, pin, is_inverting in routing_bels:
            tile_name, tile_type = self.get_tile_info_at_site(site)
            iologic_prefix = self.get_iologic_prefix(site, tile_type)
            iologic_type = iologic_prefix.split("_")[0]

            check_pins = zinv_pins[iologic_type]

            if not is_inverting and pin in check_pins:
                zinv_feature = "ZINV_{}".format(check_pins[pin])

                if iologic_type == "ILOGIC":
                    zinv_feature = "IFF.{}".format(zinv_feature)

                self.add_cell_feature((tile_name, iologic_prefix,
                                       zinv_feature))

            elif is_inverting and pin in inverting_pins:
                inv_feature = "IS_{}_INVERTED".format(pin.split("_")[0])
                self.add_cell_feature((tile_name, iologic_prefix, inv_feature))

    def handle_cmt_routing_bels(self):
        """
        Handles CMT routing bels - PLL and MMCM input pin inverters
        """
        tile_types = [
            "CMT_TOP_R_LOWER_B", "CMT_TOP_R_UPPER_T", "CMT_TOP_L_LOWER_B",
            "CMT_TOP_L_UPPER_T"
        ]
        routing_bels = self.get_routing_bels(tile_types)

        for site, bel, pin, is_inverting in routing_bels:
            tile_name, tile_type = self.get_tile_info_at_site(site)

            # Get the CMT BEL (either PLL or MMCM)
            cmt_bel = site.rsplit("_", maxsplit=1)[0]
            assert cmt_bel in ["PLLE2_ADV", "MMCME2_ADV"], cmt_bel
            # Get the CMT BEL pin
            bel_pin = pin.replace("_B", "")

            # FASM feature
            # FIXME: Weird, those ZINV_* features behave more like INV_*
            feature = "INV_{}".format(bel_pin)
            if bel_pin not in ["CLKINSEL"]:
                feature = "Z" + feature

            # Emit
            if is_inverting:
                self.add_cell_feature((tile_name, cmt_bel, feature))

    def handle_slice_bel_pins(self):
        """
        This function handles the addition of special features when specific BEL
        pins are used
        """
        tile_types = ["CLBLL_L", "CLBLL_R", "CLBLM_L", "CLBLM_R"]
        bel_pins = self.get_all_bel_pins_annotation()

        for (tile_name, site, bel), pins in bel_pins.items():

            _, tile_type = self.get_tile_info_at_site(site)
            if tile_type not in tile_types:
                continue

            slice_prefix = self.get_slice_prefix(site, tile_type)

            for pin in pins:
                if bel == "CARRY4" and pin == "CIN":
                    self.add_cell_feature((tile_name, slice_prefix,
                                           "PRECYINIT.CIN"))

    def handle_site_thru(self, site_thru_pips):
        """
        This function is currently specialized to add very specific features
        for pseudo PIPs which need to be enabled to get the correct HW behaviour
        """

        def get_feature_prefix(site_thru_feature, wire):
            regex = re.compile(site_thru_feature.regex)

            m = regex.match(wire)

            return site_thru_feature.callback(m) if m else None

        # FIXME: this information needs to be added as an annotation
        #        to the device resources
        site_thru_features = list()
        site_thru_features.append(
            ExtraFeatures(
                regex="IOI_OLOGIC([01])_D1",
                features=["OMUX.D1", "OQUSED", "OSERDES.DATA_RATE_TQ.BUF"],
                callback=lambda m: "OLOGIC_Y{}".format(m.group(1))))
        site_thru_features.append(
            ExtraFeatures(
                regex="IOI_OLOGIC([01])_T1",
                features=["ZINV_T1"],
                callback=lambda m: "OLOGIC_Y{}".format(m.group(1))))
        site_thru_features.append(
            ExtraFeatures(
                regex="[LR]IOI_ILOGIC([01])_D",
                features=["ZINV_D"],
                callback=lambda m: "ILOGIC_Y{}".format(m.group(1))))
        site_thru_features.append(
            ExtraFeatures(
                regex="CLK_HROW_CK_MUX_OUT_([LR])([0-9]+)",
                features=["IN_USE", "ZINV_CE"],
                callback=lambda m: "BUFHCE.BUFHCE_X{}Y{}".format(0 if m.group(1) == "L" else 1, m.group(2))))
        #TODO: Better handle BUFGCTRL route-through depending on the
        #      used input pin
        site_thru_features.append(
            ExtraFeatures(
                regex="CLK_BUFG_BUFGCTRL([0-9]+)_I0",
                features=[
                    "IN_USE", "ZINV_CE0", "ZINV_S0", "IS_IGNORE1_INVERTED"
                ],
                callback=
                lambda m: "BUFGCTRL.BUFGCTRL_X0Y{}".format(m.group(1))))
        site_thru_features.append(
            ExtraFeatures(
                regex="CLK_BUFG_BUFGCTRL([0-9]+)_I1",
                features=[
                    "IN_USE", "ZINV_CE1", "ZINV_S1", "IS_IGNORE0_INVERTED"
                ],
                callback=
                lambda m: "BUFGCTRL.BUFGCTRL_X0Y{}".format(m.group(1))))

        for tile, wire0, wire1 in site_thru_pips:
            for site_thru_feature in site_thru_features:
                prefix = get_feature_prefix(site_thru_feature, wire0)

                if prefix is None:
                    continue

                io_re = re.compile(".*?X[0-9]+Y([0-9]+)")
                m = io_re.match(tile)
                y_coord = int(m.group(1))
                if "SING" in tile and y_coord % 50 == 0:
                    prefix = prefix[0:-1] + "0"
                elif "SING" in tile and y_coord % 50 == 49:
                    prefix = prefix[0:-1] + "1"
                for feature in site_thru_feature.features:
                    self.add_cell_feature((tile, prefix, feature))

                break

    def handle_lut_thru(self, lut_thru_pips):
        for (net_name, site, bel), pin in lut_thru_pips.items():
            pin_name = pin["pin_name"]
            is_valid = pin["is_valid"]

            if not is_valid:
                continue

            lut_loc, lut_type = parse_lut_bel(bel)

            site_type = list(
                self.device_resources.site_name_to_site[site].keys())[0]

            lut_key = (site, lut_loc)
            if lut_key not in self.luts:
                tile_name, tile_type = self.get_tile_info_at_site(site)
                slice_site = self.get_slice_prefix(site, tile_type)
                lut_name = "{}LUT".format(lut_loc)

                self.luts[lut_key] = {
                    "data": (tile_name, slice_site, lut_name),
                    LutsEnum.LUT5: None,
                    LutsEnum.LUT6: None,
                }

            lut_enum = LutsEnum.from_str(lut_type)
            assert self.luts[lut_key][lut_enum] is None, (net_name, site, bel)

            if net_name == VCC_NET:
                lut_init = self.lut_mapper.get_const_lut_init(
                    1, site_type, bel)
            elif net_name == GND_NET:
                lut_init = self.lut_mapper.get_const_lut_init(
                    0, site_type, bel)
            else:
                lut_init = self.lut_mapper.get_phys_wire_lut_init(
                    2, site_type, "LUT1", bel, pin_name)

            self.luts[lut_key][lut_enum] = lut_init

    def handle_extra_pip_features(self, extra_pip_features):
        """
        There are some sensitive PIPs and features which mostly deal with clocking resources
        and require special handling, as without the extra features, the clocking tree configuration
        migth be incomplete, resulting in unexpected hardware behavior.

        This function handles all the special extra features corresponding to a restricted class
        of special PIPs.
        """

        def run_regex_match(extra_feature,
                            tile,
                            wire,
                            extra_wires,
                            enable_extra_wires=True):
            """
            This helper function adds the corresponding extra features based on the callback of
            the ExtraFeature element and the regex match status.

            It also adds, if enabled, a set of extra wires belonging to the input wire's
            node, that may require some extra features as well.
            """

            extra_wires_to_check = [
                "CLK_BUFG_REBUF_R_CK", "HCLK_CK_BUFHCLK", "HCLK_IOI_CK_BUFHCLK"
            ]

            if any(
                    wire.startswith(extra_wire) for extra_wire in
                    extra_wires_to_check) and enable_extra_wires:
                node_index = self.device_resources.node(tile, wire).node_index
                wires = self.device_resources.device_resource_capnp.nodes[
                    node_index].wires
                for wire_idx in wires:
                    tile_wire = self.device_resources.device_resource_capnp.wires[
                        wire_idx]
                    wire_name = self.device_resources.strs[tile_wire.wire]
                    tile_name = self.device_resources.strs[tile_wire.tile]

                    extra_wires.add((tile_name, wire_name))

            regex = re.compile(extra_feature.regex)
            m = regex.match(wire)

            if m:
                prefix = extra_feature.callback(m)

                for f in extra_feature.features:
                    f = "{}{}".format(prefix, f)
                    self.add_cell_feature((tile, f))

        # TODO: The FASM database should be reformatted so to have more
        #       regular extra PIP features.
        regexs = list()
        regexs.append(
            ExtraFeatures(
                regex="(CLK_HROW_CK_IN_[LR][0-9]+)",
                features=["_ACTIVE"],
                callback=lambda m: m.group(1)))
        regexs.append(
            ExtraFeatures(
                regex="(CLK_HROW_R_CK_GCLK[0-9]+)",
                features=["_ACTIVE"],
                callback=lambda m: m.group(1)))
        regexs.append(
            ExtraFeatures(
                regex="(HCLK_CMT_CCIO[0-9]+)",
                features=["_ACTIVE", "_USED"],
                callback=lambda m: m.group(1)))
        regexs.append(
            ExtraFeatures(
                regex="(HCLK_CMT_CK_BUFHCLK[0-9]+)",
                features=["_USED"],
                callback=lambda m: m.group(1)))
        regexs.append(
            ExtraFeatures(
                regex="CLK_BUFG_REBUF_R_CK_(GCLK[0-9]+)_BOT",
                features=["_ENABLE_ABOVE"],
                callback=lambda m: m.group(1)))
        regexs.append(
            ExtraFeatures(
                regex="CLK_BUFG_REBUF_R_CK_(GCLK[0-9]+)_TOP",
                features=["_ENABLE_BELOW"],
                callback=lambda m: m.group(1)))
        regexs.append(
            ExtraFeatures(
                regex="(HCLK_CK_BUFHCLK[0-9]+)",
                features=[""],
                callback=lambda m: "ENABLE_BUFFER.{}".format(m.group(1))))
        regexs.append(
            ExtraFeatures(
                regex="BRAM_CASCOUT_ADDR(ARD|BWR)ADDR",
                features=[""],
                callback=lambda m: "CASCOUT_{}_ACTIVE".format(m.group(1))))

        # There exist PIPs which activate other PIPs that are not present
        # in the physical netlist. These other PIPs need to be output as well.
        extra_pips = {
            "wire0": {},
            "wire1": {
                "IOI_OCLK_1": ["IOI_OCLKM_1"],
                "IOI_OCLK_0": ["IOI_OCLKM_0"],
            }
        }

        extra_wires = set()
        for tile_pips in extra_pip_features.values():
            for tile, wire0, wire1 in tile_pips:
                for extra_feature in regexs:
                    run_regex_match(extra_feature, tile, wire0, extra_wires)
                    run_regex_match(extra_feature, tile, wire1, extra_wires)

                    if wire0 in extra_pips["wire0"]:
                        for extra_wire0 in extra_pips["wire0"][wire0]:
                            self.add_pip_feature((tile, extra_wire0, wire1),
                                                 self.pip_feature_format)

                    if wire1 in extra_pips["wire1"]:
                        for extra_wire1 in extra_pips["wire1"][wire1]:
                            self.add_pip_feature((tile, wire0, extra_wire1),
                                                 self.pip_feature_format)

        # Handle extra wires
        exclude_tiles = [
            "HCLK_L", "HCLK_R", "HCLK_L_BOT_UTURN", "HCLK_R_BOT_UTURN"
        ]
        for tile, wire in extra_wires:
            if any(
                    tile.startswith(exclude_tile)
                    for exclude_tile in exclude_tiles):
                continue

            for extra_feature in regexs:
                run_regex_match(extra_feature, tile, wire, extra_wires, False)

    def handle_routes(self):
        """
        Handles all the FASM features corresponding to PIPs

        In addition, emits extra features necessary to have the clock
        resources working properly, as well the emission of site route
        thru features for pseudo PIPs
        """

        avail_lut_thrus = list()
        for _, _, _, _, bel, bel_type in self.device_resources.yield_bels():
            if bel_type in ["LUT5", "LUT6"]:
                avail_lut_thrus.append(bel)

        tile_types = [
            "HCLK_IOI3", "HCLK_L", "HCLK_R", "HCLK_L_BOT_UTURN",
            "HCLK_R_BOT_UTURN", "HCLK_CMT", "HCLK_CMT_L", "CLK_HROW_TOP_R",
            "CLK_HROW_BOT_R", "CLK_BUFG_REBUF", "BRAM_L", "BRAM_R", "LIOI3",
            "LIOI3_SING", "LIOI3_TBYTETERM", "LIOI3_TBYTESRC", "RIOI3",
            "RIOI3_SING", "RIOI3_TBYTETERM", "RIOI3_TBYTESRC"
        ]
        extra_pip_features = dict(
            (tile_type, set()) for tile_type in tile_types)

        site_thru_pips, lut_thru_pips = self.fill_pip_features(
            self.pip_feature_format, extra_pip_features, avail_lut_thrus)

        self.handle_extra_pip_features(extra_pip_features)
        self.handle_site_thru(site_thru_pips)
        self.handle_lut_thru(lut_thru_pips)

    def fill_features(self):
        self.pip_feature_format = "{tile}.{wire1}.{wire0}"

        # Handle LUTs first (needed for LUT-thru routing)
        self.handle_luts()
        # Handling PIPs and Route-throughs
        self.handle_routes()

        # Handling BELs
        self.handle_brams()
        self.handle_cmts()
        self.handle_clock_resources()
        self.handle_ios()
        self.handle_iologic()
        self.handle_slice_ff()

        # Handling routing BELs
        self.handle_slice_routing_bels()
        self.handle_bram_routing_bels()
        self.handle_ioi_routing_bels()
        self.handle_cmt_routing_bels()

        # Handling bel pins
        self.handle_slice_bel_pins()

        # Emit LUT features. This needs to be done at last as
        # LUT features depend also on LUT route-thru
        self.add_lut_features()
