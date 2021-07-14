#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2021 The SymbiFlow Authors.
#
# Use this source code is governed by a ISC-style
# license that can be found in LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
"""
    This file contains script to compare 2 timing analysis result files.
    First file is used as baseline, second one is compared against base.
    Results are as follows:
    (base_line_net_name, compared_net_name) (relative_value, baseline_value, compared_value)
"""

import argparse
import sys

# ============================================================================


def main():

    parser = argparse.ArgumentParser(
        description="Performs static timing analysis")
    parser.add_argument(
        "--base_timing", required=True, help="Path to file with base timings")
    parser.add_argument(
        "--compare_timing",
        required=True,
        help="Path to file with timings to compare")
    parser.add_argument(
        "--name_mapping",
        help=
        "Path to file with mappings from compare_timing net name to base_timings net name"
    )
    parser.add_argument(
        "--output_file", help="Path to file with results", default=None)

    args = parser.parse_args()

    if args.output_file is not None:
        output_file = open(args.output_file, 'w')
    else:
        output_file = sys.stdout

    baseline = {}
    with open(args.base_timing, 'r') as f:
        for line in f.readlines():
            line = line.split()
            baseline[line[0]] = int(float(line[1]))

    comp = {}
    with open(args.compare_timing, 'r') as f:
        for line in f.readlines():
            line = line.split()
            comp[line[0]] = int(float(line[1]))

    map_net = {}
    if args.name_mapping is not None:
        with open(args.name_mapping, 'r') as f:
            for line in f.readlines():
                line = line.split()
                map_net[line[0]] = line[1]

    not_found = {}
    net_compare = {}

    for key, value in comp.items():
        n_key = key
        if key in map_net.keys():
            n_key = map_net[key]
        if n_key not in baseline.keys():
            not_found[key] = value
            continue
        base_v = baseline[n_key]
        if base_v != 0:
            net_compare[(n_key, key)] = (value / base_v, base_v, value)
        elif value == 0:
            net_compare[(n_key, key)] = (1, base_v, value)
        else:
            net_compare[(n_key, key)] = (value, base_v, value)
        baseline.pop(n_key)

    for key, value in net_compare.items():
        print(key, value, file=output_file)

    print("Nets not mapped:", file=output_file)
    for key, value in not_found.items():
        print("\t", key, value, file=output_file)

    print("Nets not used:", file=output_file)
    for key, value in baseline.items():
        print("\t", key, value, file=output_file)


# =============================================================================

if __name__ == "__main__":
    main()
