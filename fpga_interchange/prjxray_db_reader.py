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

import argparse
import os
import json
import re
import itertools
from copy import deepcopy

from collections import defaultdict

from sdf_timing import sdfparse
from sdf_timing.utils import get_scale_seconds

CAPACITANCE = 1e-9  # convert from prjxray internal values to farads
RESISTANCE = 1e-6  # convert from prjxray internal values to ohms
DELAY = 1e-9  # convert from ns to s

# =============================================================================


def expand_pattern(pattern):
    """
    Expands a simple reges pattern containing multiple "[<chars>]" closures
    to all possible combinations.
    """
    expr = r"\[([^\[\]]+)\]"

    groups = []
    for match in re.finditer(expr, pattern):
        groups.append(match.group(1))

    strings = []
    for subs in itertools.product(*groups):
        s = str(pattern)
        for i, sub in enumerate(subs):
            s = re.sub(expr, sub, s, 1)
        strings.append(s)

    return strings


def get_timings(site, spec, sdf_data):
    """
    Given a cell and instance specification as "<cell>@<instance>" finds and
    returns the timings.
    """

    assert spec.count("@") == 1, spec
    cell, instance = spec.split("@", maxsplit=1)

    if cell not in sdf_data:
        print("ERROR: No SDF data for cell '{}'".format(cell))
        return None

    assert instance.count("/") <= 1, (cell, instance)
    if "/" in instance:
        site, bel = instance.split("/")
    else:
        site, bel = instance, None

    if site not in sdf_data[cell]:
        print("ERROR: No SDF data for cell '{}', site '{}'".format(cell, site))
        print(sdf_data[cell].keys())
        return None

    if bel not in sdf_data[cell][site]:
        print("ERROR: No SDF data for cell '{}', site '{}', bel '{}'".format(cell, site, bel))
        return None

    return sdf_data[cell][site][bel]


def map_timings(timings, pin_map):
    """
    Applies pin map to SDF timings dict
    """
    mapped_timings = dict()
    for key, data in timings.items():

        data = deepcopy(data)
        for k in ["from_pin", "to_pin"]:
            data[k] = pin_map.get(data[k], data[k])

        key = "{}_{}_{}".format(data["type"], data["from_pin"], data["to_pin"])
        mapped_timings[key] = data

    return mapped_timings


def merge_timings(timings, overlay):
    """
    Overlays timing data from the "new" dict tree onto the existing "timing"
    one.
    """

    def walk(curr, new):

        assert type(curr) == type(new), (type(curr), type(new))

        # Non-dict, just replace
        if not isinstance(new, dict):
            return new

        # Merge dicts recursively
        for k, v in new.items():
            if k not in curr:
                curr[k] = v
            else:
                curr[k] = walk(curr[k], v)

        return curr

    return walk(timings, overlay)

# =============================================================================


class prjxray_db_reader:
    def __init__(self, timing_dir, sdf_map_file = None):
        self.timing_dir = timing_dir

        self.sdf_map = dict()
        if sdf_map_file is not None:
            with open(sdf_map_file, "r") as fp:
                self.sdf_map = json.load(fp)


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

        # Scan and parse SDFs
        sdf_data = dict()

        sdf_dir = os.path.join(self.timing_dir, "timings")
        for fname in os.listdir(sdf_dir):

            if not fname.lower().endswith(".sdf"):
                continue

            sdf_file = os.path.join(sdf_dir, fname)
            if not os.path.isfile(sdf_file):
                continue

            tile_type, _ = os.path.splitext(fname)

            if tile_type not in return_dict:
                print("WARNING: No tile '{}'".format(tile_type))
                continue

            with open(sdf_file) as f:
                sdf = f.read()

            timings = sdfparse.parse(sdf)
            timings = self.process_sdf_data(timings)

            sdf_data = merge_timings(sdf_data, timings)

        # Collect timings
        timings_dict = dict()
        for site, site_data in self.sdf_map.items():

            if site not in timings_dict:
                timings_dict[site] = dict()

            for pattern, cell_data in site_data.items():

                # Get BEL pin map
                pin_map = cell_data.get("pin_map", dict())

                # Expand the BEL name pattern
                bels = expand_pattern(pattern)
                for bel in bels:

                    if bel not in timings_dict[site]:
                        timings_dict[site][bel] = dict()

                    # Get default timing data if any
                    defaults = dict()
                    if "default" in cell_data:
                        for spec in cell_data["default"]:
                            spec = spec.format(bel=bel)
                            ts = get_timings(site, spec, sdf_data)
                            if ts is not None:
                                ts = map_timings(ts, pin_map)
                                defaults = merge_timings(defaults, ts)

                        # Store timing data for any cell
                        timings_dict[site][bel][None] = defaults

                    # Overlay subsequent cell-specific entries
                    for cell, data in cell_data.items():
                        if cell in ["pin_map", "default"]:
                            continue

                        timings = deepcopy(defaults)
                        for spec in data:
                            spec = spec.format(bel=bel)
                            ts = get_timings(site, spec, sdf_data)
                            if ts is not None:
                                ts = map_timings(ts, pin_map)
                                timings = merge_timings(timings, ts)

                        # Store timing data for the specific cell
                        timings_dict[site][bel][cell] = timings

        return return_dict, timings_dict


    def process_sdf_data(self, data):

        # Timescale. Assume 1ns if not present in the header
        scale = get_scale_seconds(data["header"].get("timescale", "1ns"))

        def apply_timescale(d):
            if isinstance(d, dict):
                new_d = {}
                for k, v in d.items():
                    new_d[k] = apply_timescale(v)
                return new_d
            elif isinstance(d, float):
                return d * scale
            else:
                return d

        # Group timing data by cell, site and bel. Scale values to seconds
        timings = {}
        for cell, instances in data["cells"].items():
            timings[cell] = defaultdict(dict)
            for instance, paths in instances.items():

                # Get site and bell name if possible
                assert instance.count("/") <= 1, (cell, instance)
                if "/" in instance:
                    site, bel = instance.split("/")
                else:
                    site, bel = instance, None

                # Filter timing data
                keys = {"type", "from_pin", "to_pin", "from_pin_edge", "to_pin_edge", "delay_paths"}
                paths = {t: {k: v for k, v in d.items() if k in keys} for t, d in paths.items()}

                # Apply timescale
                for key, path in paths.items():
                    paths[key] = apply_timescale(path)

                timings[cell][site][bel] = paths

            timings[cell] = dict(timings[cell])

        return timings


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db-root",
        type=str,
        required=True,
        help="Project XRay database root path"
    )
    parser.add_argument(
        "--sdf-map",
        type=str,
        required=True,
        help="Map of SDF timing entries to cell @ site and bel"
    )

    args = parser.parse_args()

    # Get data
    reader = prjxray_db_reader(args.db_root, args.sdf_map)
    routing_data, timings_dict = reader.extract_data()

    # Dump data (not all of it of course)
    print("Routing timing:")
    for tile, tile_data in routing_data.items():
        print("", tile)
        print(" ", "{} wires".format(len(tile_data['wires'])))
        print(" ", "{} pips".format(len(tile_data['pips'])))

        for site, site_data in tile_data['sites'].items():
            print(" ", "site '{}' {} pins".format(site, len(site_data)))

    print("Cell timings (site/bel/cell):")
    for site, bels in timings_dict.items():
        print("", site)
        for bel, cells in bels.items():
            print(" ", bel)
            for cell, timings in cells.items():
                print("  ", "any" if cell is None else cell)
                for key in timings:
                    print("   ", key)
