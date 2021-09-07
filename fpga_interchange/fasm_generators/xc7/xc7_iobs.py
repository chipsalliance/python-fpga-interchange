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
"""
This file contains all the currently supported IOSTANDARD, slewand DRIVE combinations that
translate into specific features.

This is a temporary solution before adding all the information necessary to generate a
correct FASM out of a physical netlist directly without using additional data files.
"""

iob_settings = {
    "LVCMOS12_LVCMOS15_LVCMOS18.IN": {
        "iostandards": {
            'LVCMOS12': [],
            'LVCMOS15': [],
            'LVCMOS18': []
        },
        "slews": [],
    },
    "LVCMOS12_LVCMOS15_LVCMOS18_LVCMOS25_LVCMOS33_LVDS_25_LVTTL_SSTL135_SSTL15_TMDS_33.IN_ONLY":
    {
        "iostandards": {
            'LVCMOS12': [],
            'LVCMOS15': [],
            'LVCMOS18': [],
            'LVCMOS25': [],
            'LVCMOS33': [],
            'LVTTL': [],
            'SSTL135': [],
            'SSTL15': [],
            'DIFF_SSTL135': [],
            'DIFF_SSTL15': []
        },
        "slews": [],
    },
    "LVCMOS12_LVCMOS15_LVCMOS18_LVCMOS25_LVCMOS33_LVTTL.SLEW.FAST": {
        "iostandards": {
            'LVCMOS12': [],
            'LVCMOS15': [],
            'LVCMOS18': [],
            'LVCMOS25': [],
            'LVCMOS33': [],
            'LVTTL': []
        },
        "slews": ['FAST'],
    },
    "LVCMOS12_LVCMOS15_LVCMOS18_SSTL135_SSTL15.STEPDOWN": {
        "iostandards": {
            'LVCMOS12': [],
            'LVCMOS15': [],
            'LVCMOS18': [],
            'SSTL135': [],
            'SSTL15': [],
            'DIFF_SSTL135': [],
            'DIFF_SSTL15': []
        },
        "slews": [],
    },
    "LVCMOS25_LVCMOS33_LVTTL.IN": {
        "iostandards": {
            'LVCMOS25': [],
            'LVCMOS33': [],
            'LVTTL': []
        },
        "slews": [],
    },
    "SSTL135_SSTL15.IN": {
        "iostandards": {
            'SSTL135': [],
            'SSTL15': []
        },
        "slews": [],
    },
    "LVCMOS12.DRIVE.I12": {
        "iostandards": {
            'LVCMOS12': [12]
        },
        "slews": [],
    },
    "LVCMOS12.DRIVE.I4": {
        "iostandards": {
            'LVCMOS12': [4]
        },
        "slews": [],
    },
    "LVCMOS12_LVCMOS15_LVCMOS18_LVCMOS25_LVCMOS33_LVTTL_SSTL135_SSTL15.SLEW.SLOW":
    {
        "iostandards": {
            'LVCMOS12': [],
            'LVCMOS15': [],
            'LVCMOS18': [],
            'LVCMOS25': [],
            'LVCMOS33': [],
            'LVTTL': [],
            'SSTL135': [],
            'SSTL15': [],
            'DIFF_SSTL135': [],
            'DIFF_SSTL15': []
        },
        "slews": ['SLOW'],
    },
    "LVCMOS12_LVCMOS25.DRIVE.I8": {
        "iostandards": {
            'LVCMOS12': [8],
            'LVCMOS25': [8]
        },
        "slews": [],
    },
    "LVCMOS15.DRIVE.I12": {
        "iostandards": {
            'LVCMOS15': [12]
        },
        "slews": [],
    },
    "LVCMOS15.DRIVE.I8": {
        "iostandards": {
            'LVCMOS15': [8]
        },
        "slews": [],
    },
    "LVCMOS15_LVCMOS18_LVCMOS25.DRIVE.I4": {
        "iostandards": {
            'LVCMOS15': [4],
            'LVCMOS18': [4],
            'LVCMOS25': [4]
        },
        "slews": [],
    },
    "LVCMOS15_SSTL15.DRIVE.I16_I_FIXED": {
        "iostandards": {
            'LVCMOS15': [16],
            'SSTL15': [],
            'DIFF_SSTL15': []
        },
        "slews": [],
    },
    "LVCMOS18.DRIVE.I12_I8": {
        "iostandards": {
            'LVCMOS18': [8, 12]
        },
        "slews": [],
    },
    "LVCMOS18.DRIVE.I16": {
        "iostandards": {
            'LVCMOS18': [16]
        },
        "slews": [],
    },
    "LVCMOS18.DRIVE.I24": {
        "iostandards": {
            'LVCMOS18': [24]
        },
        "slews": [],
    },
    "LVCMOS25.DRIVE.I12": {
        "iostandards": {
            'LVCMOS25': [12]
        },
        "slews": [],
    },
    "LVCMOS25.DRIVE.I16": {
        "iostandards": {
            'LVCMOS25': [16]
        },
        "slews": [],
    },
    "LVCMOS33.DRIVE.I16": {
        "iostandards": {
            'LVCMOS33': [16]
        },
        "slews": [],
    },
    "LVCMOS33_LVTTL.DRIVE.I12_I16": {
        "iostandards": {
            'LVCMOS33': [12],
            'LVTTL': [16]
        },
        "slews": [],
    },
    "LVCMOS33_LVTTL.DRIVE.I12_I8": {
        "iostandards": {
            'LVCMOS33': [8],
            'LVTTL': [8, 12]
        },
        "slews": [],
    },
    "LVCMOS33_LVTTL.DRIVE.I4": {
        "iostandards": {
            'LVCMOS33': [4],
            'LVTTL': [4]
        },
        "slews": [],
    },
    "LVTTL.DRIVE.I24": {
        "iostandards": {
            'LVTTL': [24]
        },
        "slews": [],
    },
    "SSTL135.DRIVE.I_FIXED": {
        "iostandards": {
            'SSTL135': [],
            'DIFF_SSTL135': []
        },
        "slews": [],
    },
    "SSTL135_SSTL15.SLEW.FAST": {
        "iostandards": {
            'SSTL135': [],
            'SSTL15': [],
            'DIFF_SSTL135': [],
            'DIFF_SSTL15': []
        },
        "slews": ['FAST'],
    },
    "LVDS_25_SSTL135_SSTL15.IN_DIFF": {
        "iostandards": {
            'DIFF_SSTL135': [],
            'DIFF_SSTL15': []
        },
        "slews": [],
    },
}
