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
    This file contains simple script for patching device with timing data.

    It uses simple abstraction layer. It constructs specialized class,
    for given architecture, passing database path, then it calls extract_data method.
    That method must return dictionary with keys being tile_type names.
    Data stored at each key must be dictionary with keys: "wires", "pips", "sites".
    "wires" entry must hold dictionary with keys being wire name, and data being RC model
    "pips" entry must hold dictionary with keys being pair (wire0 name, wire1 name) and data being pip model
    "sites" entry must hold dictionary with keys being site name and data being
        dictionary with keys being sitePort name and value being model of this port

    So far this script only adds delay models to site ports, PIPs and nodes.
    But adding support for cells shouldn't be hard thanks to abstraction layer.
"""
import argparse

from fpga_interchange.interchange_capnp import read_capnp_file,\
        write_capnp_file

from fpga_interchange.convert import get_schema
from fpga_interchange.prjxray_db_reader import prjxray_db_reader
import os
import json


def create_wire_to_node_map(device):
    wire_map = {}
    node_to_model = {}
    for node in device.nodes:
        node_to_model[node] = (tuple([0] * 6), tuple([0] * 6))
        for wire in node.wires:
            wire_map[wire] = node
    return node_to_model, wire_map


def create_tile_type_wire_name_to_wire_list(device):
    tile_tileType_map = {}
    for tile in device.tileList:
        tile_tileType_map[tile.name] = tile.type
    tileType_wireName_wireList_map = {}
    for i, wire in enumerate(device.wires):
        tileType = tile_tileType_map[wire.tile]
        key = (tileType, wire.wire)
        if key not in tileType_wireName_wireList_map.keys():
            tileType_wireName_wireList_map[key] = []
        tileType_wireName_wireList_map[key].append(i)
    return tileType_wireName_wireList_map


def create_string_to_dev_string_map(device):
    string_map = {}
    for i, string in enumerate(device.strList):
        string_map[string] = i
    return string_map


def create_tile_type_name_to_tile_type(device):
    tileType_name_tileType_map = {}
    for i, tile in enumerate(device.tileTypeList):
        tileType_name_tileType_map[tile.name] = i
    return tileType_name_tileType_map


def create_tile_type_wire0_wire1_pip_map(device):
    tileType_wires_pip_map = {}
    for i, tile in enumerate(device.tileTypeList):
        for pip in tile.pips:
            wire0 = tile.wires[pip.wire0]
            wire1 = tile.wires[pip.wire1]
            key = (i, wire0, wire1)
            tileType_wires_pip_map[key] = pip
    return tileType_wires_pip_map


def create_site_name_to_site_type_map(device):
    siteName_siteType_map = {}
    for i, site in enumerate(device.siteTypeList):
        siteName_siteType_map[site.name] = i
    return siteName_siteType_map


def create_site_type_name_to_site_pin_map(device):
    siteType_name_sitePin = {}
    for i, site in enumerate(device.siteTypeList):
        for sitePin in site.pins:
            siteType_name_sitePin[(i, sitePin.name)] = sitePin
    return siteType_name_sitePin


def populate_corner_model(corner_model, fast_min, fast_typ, fast_max, slow_min,
                          slow_typ, slow_max):
    fields = ['min', 'typ', 'max']
    fast = [fast_min, fast_typ, fast_max]
    slow = [slow_min, slow_typ, slow_max]
    if any(x is not None for x in fast):
        corner_model.fast.init('fast')
    if any(x is not None for x in slow):
        corner_model.slow.init('slow')
    for i, field in enumerate(fields):
        if fast[i] is not None:
            x = getattr(corner_model.fast.fast, field)
            setattr(x, field, fast[i])
    for i, field in enumerate(fields):
        if slow[i] is not None:
            x = getattr(corner_model.slow.slow, field)
            setattr(x, field, slow[i])


def main():
    parser = argparse.ArgumentParser(
        description="Add timing information to Device")

    parser.add_argument("--schema_dir", required=True)
    parser.add_argument("--timing_dir", required=True)
    parser.add_argument("--family", required=True)
    parser.add_argument("device")
    parser.add_argument("patched_device")

    args = parser.parse_args()

    device_schema = get_schema(args.schema_dir, "device")
    with open(args.device, 'rb') as f:
        dev = read_capnp_file(device_schema, f)

    dev = dev.as_builder()

    node_model_map, wire_node_map = create_wire_to_node_map(dev)
    tileType_wire_name_wire_list_map = create_tile_type_wire_name_to_wire_list(
        dev)
    string_map = create_string_to_dev_string_map(dev)
    tile_name_tileType_map = create_tile_type_name_to_tile_type(dev)
    tileType_wires_pip_map = create_tile_type_wire0_wire1_pip_map(dev)
    siteName_siteType_map = create_site_name_to_site_type_map(dev)
    siteType_name_sitePin_map = create_site_type_name_to_site_pin_map(dev)

    tile_type_name_to_number = {}
    for i, tileType in enumerate(dev.tileTypeList):
        name = dev.strList[tileType.name]
        tile_type_name_to_number[name] = i

    pip_models = {}

    family_map = {"xc7": prjxray_db_reader}

    timing_dir = args.timing_dir
    timing_reader = family_map[args.family](timing_dir)
    timing_data = timing_reader.extract_data()
    for tile, _data in timing_data.items():
        if tile not in string_map:
            continue
        tile_name = string_map[tile]
        tileType = tile_name_tileType_map[tile_name]
        for name, data in _data['wires'].items():
            wire_name = string_map[name]
            for wire in tileType_wire_name_wire_list_map[(tileType,
                                                          wire_name)]:
                if wire not in wire_node_map:
                    continue
                node = wire_node_map[wire]
                model = node_model_map[node]
                res = list(model[0])
                cap = list(model[1])
                for i in range(len(res)):
                    res[i] += data[0][i]
                for i in range(len(cap)):
                    cap[i] += data[1][i]
                model = (tuple(res), tuple(cap))
                node_model_map[node] = model

        for old_key, data in _data['pips'].items():
            wire0 = string_map[old_key[0]]
            wire1 = string_map[old_key[1]]
            key = (tileType, wire0, wire1)
            if key not in tileType_wires_pip_map:
                continue
            pip = tileType_wires_pip_map[key]
            pip_models[pip] = data

        for site, data in _data['sites'].items():
            siteType = siteName_siteType_map[string_map[site]]
            for sitePin, model in data.items():
                sitePin_obj = siteType_name_sitePin_map[(siteType,
                                                         string_map[sitePin])]
                if model[0][0] is not None and model[0][0] == 'r':
                    sitePin_obj.model.init('resistance')
                    corner_model = sitePin_obj.model.resistance
                    populate_corner_model(corner_model, *model[0][1])
                elif model[0][0] is not None and model[0][0] == 'c':
                    sitePin_obj.model.init('capacitance')
                    corner_model = sitePin_obj.model.capacitance
                    populate_corner_model(corner_model, *model[0][1])

                sitePin_obj.init('delay')
                corner_model = sitePin_obj.delay
                populate_corner_model(corner_model, *model[1])

    timing_set = set()
    for timing in node_model_map.values():
        timing_set.add(timing)
    timing_dict = {timing: i for i, timing in enumerate(timing_set)}
    dev.init("nodeTimings", len(timing_dict))
    for model, i in timing_dict.items():
        corner_model = dev.nodeTimings[i].resistance
        populate_corner_model(corner_model, *model[0])
        corner_model = dev.nodeTimings[i].capacitance
        populate_corner_model(corner_model, *model[1])

    for node, timing in node_model_map.items():
        node.nodeTiming = timing_dict[timing]

    timing_set = set()
    for model in pip_models.values():
        timing_set.add(model)
    timing_dict = {timing: i for i, timing in enumerate(timing_set)}
    dev.init("pipTimings", len(timing_dict))
    for model, i in timing_dict.items():
        pipTiming = dev.pipTimings[i]
        corner_model = pipTiming.inputCapacitance
        populate_corner_model(corner_model, *model[0])

        corner_model = pipTiming.internalCapacitance
        populate_corner_model(corner_model, *model[1])

        corner_model = pipTiming.internalDelay
        populate_corner_model(corner_model, *model[2])

        corner_model = pipTiming.outputResistance
        populate_corner_model(corner_model, *model[3])

        corner_model = pipTiming.outputCapacitance
        populate_corner_model(corner_model, *model[4])

    for pip, timing in pip_models.items():
        pip.timing = timing_dict[timing]

    with open(args.patched_device, "wb") as fp:
        write_capnp_file(dev, fp)


if __name__ == "__main__":
    main()
