#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2021 The SymbiFlow Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC

import os
import json


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
            print(_file, tile_data["tile_type"])
            tile_name = tile_data['tile_type']
            tile_dict = {}
            tile_dict['wires'] = {}
            for name, data in tile_data['wires'].items():
                if data is None:
                    continue
                wire_name = name
                tile_dict['wires'][wire_name] = (
                    tuple([float(data['res']) * 1e-6] * 6),
                    tuple([float(data['cap']) * 1e-9] * 6))

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
                        [float(model_values['in_cap']) * 1e-9] * 6)
                delays = tuple([None] * 6)
                if model_values['delay'] is not None:
                    delays = (float(model_values['delay'][0]) * 1e-9, None,
                              float(model_values['delay'][1]) * 1e-9,
                              float(model_values['delay'][2]) * 1e-9, None,
                              float(model_values['delay'][3]) * 1e-9)
                output_cap = tuple([None] * 6)

                output_res = tuple([None] * 6)
                if model_values['res'] is not None:
                    output_res = tuple([float(model_values['res']) * 1e-6] * 6)

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
                        values = ('r', tuple([float(dic['res']) * 1e-6] * 6))
                        delays = (float(dic['delay'][0]) * 1e-9, None,
                                  float(dic['delay'][1]) * 1e-9,
                                  float(dic['delay'][2]) * 1e-9, None,
                                  float(dic['delay'][3]) * 1e-9)
                    else:
                        values = ('c', tuple([float(dic['cap']) * 1e-9] * 6))
                        delays = (float(dic['delay'][0]) * 1e-9, None,
                                  float(dic['delay'][1]) * 1e-9,
                                  float(dic['delay'][2]) * 1e-9, None,
                                  float(dic['delay'][3]) * 1e-9)
                    tile_dict['sites'][siteType][sitePin] = (values, delays)
            return_dict[tile_name] = tile_dict
        return return_dict


if __name__ == "__main__":
    print("This file conatins reader class for prjxray-db-timings")
