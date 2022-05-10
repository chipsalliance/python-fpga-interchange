#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2021 The F4PGA Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
"""
    This file defines PRJXRAY database timing reader.

    The prjxray_db_reader is abstraction layer for device_timing_patchin.py
    so that later script doesn't have to know every odds and ends
    of the database timing models are taken from.

    Extract_data method is used to read and extract data from PRJXRAY
    timing database. It returns dictionary compatible with device_timing_patching.py

    So far it only extracts data regarding interconnect,
    pip and site port delay/RC models. The ultimate goal is to support
    delays inside sites.
"""

import os
import json

CAPACITANCE = 1e-9  # convert from prjxray internal values to farads
RESISTANCE = 1e-6  # convert from prjxray internal values to ohms
DELAY = 1e-9  # convert from ns to s


class prjxray_db_reader:
    def __init__(self, timing_dir):
        self.timing_dir = timing_dir

    def extract_data(self):
        return_dict = {}
        for i, _file in enumerate(os.listdir(self.timing_dir)):
            if not os.path.isfile(os.path.join(
                    self.timing_dir, _file)) or 'tile_type_' not in _file:
                continue
            with open(os.path.join(self.timing_dir, _file), 'r') as f:
                tile_data = json.load(f)
            tile_name = tile_data['tile_type']
            tile_dict = {}
            tile_dict['wires'] = {}
            for name, data in tile_data['wires'].items():
                if data is None:
                    continue
                wire_name = name
                tile_dict['wires'][wire_name] = (
                    tuple([float(data['res']) * RESISTANCE] * 6),
                    tuple([float(data['cap']) * CAPACITANCE] * 6))

            tile_dict['pips'] = {}
            for data in tile_data['pips'].values():
                wire0 = data['src_wire']
                wire1 = data['dst_wire']
                key = (wire0, wire1)
                model_values = data['src_to_dst']
                input_cap = tuple([None] * 6)
                internal_cap = tuple([None] * 6)
                if model_values['in_cap'] is not None:
                    internal_cap = tuple(
                        [float(model_values['in_cap']) * CAPACITANCE] * 6)
                delays = tuple([None] * 6)
                if model_values['delay'] is not None:
                    delays = (float(model_values['delay'][0]) * DELAY, None,
                              float(model_values['delay'][1]) * DELAY,
                              float(model_values['delay'][2]) * DELAY, None,
                              float(model_values['delay'][3]) * DELAY)
                output_cap = tuple([None] * 6)

                output_res = tuple([None] * 6)
                if model_values['res'] is not None:
                    output_res = tuple(
                        [float(model_values['res']) * RESISTANCE] * 6)

                tile_dict['pips'][key] = (input_cap, internal_cap, delays,
                                          output_res, output_cap)

            tile_dict['sites'] = {}
            for site in tile_data['sites']:
                siteType = site['type']
                tile_dict['sites'][siteType] = {}
                for sitePin, dic in site['site_pins'].items():
                    values = None
                    delays = None
                    if dic is None:
                        delays = tuple([None] * 6)
                        values = (None, tuple([None] * 6))
                    elif 'res' in dic.keys():
                        values = ('r',
                                  tuple([float(dic['res']) * RESISTANCE] * 6))
                        delays = (float(dic['delay'][0]) * DELAY, None,
                                  float(dic['delay'][1]) * DELAY,
                                  float(dic['delay'][2]) * DELAY, None,
                                  float(dic['delay'][3]) * DELAY)
                    else:
                        values = ('c',
                                  tuple([float(dic['cap']) * CAPACITANCE] * 6))
                        delays = (float(dic['delay'][0]) * DELAY, None,
                                  float(dic['delay'][1]) * DELAY,
                                  float(dic['delay'][2]) * DELAY, None,
                                  float(dic['delay'][3]) * DELAY)
                    tile_dict['sites'][siteType][sitePin] = (values, delays)
            return_dict[tile_name] = tile_dict
        return return_dict


if __name__ == "__main__":
    print("This file conatins reader class for prjxray-db-timings")
