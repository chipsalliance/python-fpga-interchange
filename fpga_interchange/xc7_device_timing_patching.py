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

import argparse

from fpga_interchange.interchange_capnp import read_capnp_file,\
        write_capnp_file

from fpga_interchange.convert import get_schema
import os
import json


def create_wire_to_node_map(device):
    wire_map = {}
    node_to_model = {}
    for node in device.nodes:
        node_to_model[node] = (0,0)
        for wire in node.wires:
            wire_map[wire] = node
    return node_to_model, wire_map

def create_tileType_wireName_to_wire_list(device):
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

def create_tileType_name_to_tileType(device):
    tileType_name_tileType_map = {}
    for i, tile in enumerate(device.tileTypeList):
        tileType_name_tileType_map[tile.name] = i
    return tileType_name_tileType_map

def create_tileType_wire0_wire1_pip_map(device):
    tileType_wires_pip_map = {}
    for i, tile in enumerate(device.tileTypeList):
        for pip in tile.pips:
            wire0 = tile.wires[pip.wire0]
            wire1 = tile.wires[pip.wire1]
            key = (i, wire0, wire1)
            tileType_wires_pip_map[key] = pip
    return tileType_wires_pip_map

def create_siteName_to_siteType_map(device):
    siteName_siteType_map = {}
    for i, site in enumerate(device.siteTypeList):
        siteName_siteType_map[site.name] = i
    return siteName_siteType_map

def create_siteType_name_to_sitePin_map(device):
    siteType_name_sitePin = {}
    for i, site in enumerate(device.siteTypeList):
        for sitePin in site.pins:
            siteType_name_sitePin[(i,sitePin.name)] = sitePin
    return siteType_name_sitePin

def main():
    parser = argparse.ArgumentParser(description="Add timing information to Xilinx 7 series ")

    parser.add_argument("--schema_dir", required=True)
    parser.add_argument("--timing_dir", required=True)
    parser.add_argument("device")
    parser.add_argument("patched_device")

    args = parser.parse_args()

    timing_dir = args.timing_dir
    device_schema = get_schema(args.schema_dir, "device")
    with open(args.device, 'rb') as f:
        dev = read_capnp_file(device_schema, f)

    dev = dev.as_builder()

    node_model_map, wire_node_map = create_wire_to_node_map(dev)
    tileType_wire_name_wire_list_map = create_tileType_wireName_to_wire_list(dev)
    string_map = create_string_to_dev_string_map(dev)
    tile_name_tileType_map = create_tileType_name_to_tileType(dev)
    tileType_wires_pip_map = create_tileType_wire0_wire1_pip_map(dev)
    siteName_siteType_map = create_siteName_to_siteType_map(dev)
    siteType_name_sitePin_map = create_siteType_name_to_sitePin_map(dev)

    tile_type_name_to_number = {}
    for i, tileType in enumerate(dev.tileTypeList):
        name = dev.strList[tileType.name]
        tile_type_name_to_number[name] = i

    pip_models = {}

    for i, _file in enumerate(os.listdir(timing_dir)):
        if os.path.isfile(os.path.join(timing_dir, _file)) and 'tile_type_' in _file:
            with open(os.path.join(timing_dir, _file), 'r') as f:
                tile_data = json.load(f)
            print(_file, tile_data["tile_type"])
            if tile_data['tile_type'] not in string_map:
                continue
            tile_name = string_map[tile_data['tile_type']]
            tileType = tile_name_tileType_map[tile_name]
            for name, data in tile_data['wires'].items():
                if data is None:
                    continue
                wire_name = string_map[name]
                for wire in tileType_wire_name_wire_list_map[(tileType, wire_name)]:
                    if wire not in wire_node_map:
                        continue
                    node = wire_node_map[wire]
                    model = node_model_map[node]
                    model = (model[0] + float(data['cap']) * 1e-9,
                             model[1] + float(data['res']) * 1e-6)
                    node_model_map[node] = model
            for data in tile_data['pips'].values():
                wire0 = string_map[data['src_wire']]
                wire1 = string_map[data['dst_wire']]
                key = (tileType, wire0, wire1)
                if key not in tileType_wires_pip_map:
                    continue
                pip = tileType_wires_pip_map[key]
                model_values = data['src_to_dst']
                delays = (0, 0, 0, 0)
                if model_values['delay'] is not None:
                    delays = tuple(model_values['delay'])
                cap = 0
                if model_values['in_cap'] is not None:
                    cap = float(model_values['in_cap'])
                res = 0
                if model_values['res'] is not None:
                    res = float(model_values['res'])
                pip_models[pip] = (cap, res, delays)
            for site in tile_data['sites']:
                siteType = siteName_siteType_map[string_map[site['type']]]
                for sitePin, dic in site['site_pins'].items():
                    sitePin_obj = siteType_name_sitePin_map[(siteType, string_map[sitePin])]
                    if dic is None:
                        dic = {}
                        dic['delay'] = [0, 0, 0, 0]
                    elif 'res' in dic.keys():
                        sitePin_obj.model.init('resistance')
                        sitePin_obj.model.resistance.slow.init('slow')
                        sitePin_obj.model.resistance.slow.slow.typ.typ = float(dic['res']) * 1e-6
                    else:
                        sitePin_obj.model.init('capacitance')
                        sitePin_obj.model.capacitance.slow.init('slow')
                        sitePin_obj.model.capacitance.slow.slow.typ.typ = float(dic['cap']) * 1e-6
                    sitePin_obj.init('delay')
                    corner_model = sitePin_obj.delay
                    for i, delay in enumerate(dic['delay']):
                        delay = float(delay) * 1e-9
                        attr1 = "fast" if i < 2 else "slow"
                        attr2 = "min" if i % 2 == 0 else "max"
                        v = getattr(corner_model, attr1)
                        if v.which() != attr1:
                            v.init(attr1)
                        v = getattr(v, attr1)
                        v = getattr(v, attr2)
                        setattr(v, attr2, delay)

    timing_set = set()
    for timing in node_model_map.values():
        timing_set.add(timing)
    timing_dict = {timing: i for i, timing in enumerate(timing_set)}
    dev.init("nodeTimings", len(timing_dict))
    for model, i in timing_dict.items():
        corner_model = dev.nodeTimings[i]
        corner_model.capacitance.slow.init("slow")
        corner_model.capacitance.slow.slow.typ.typ = model[0]
        corner_model.resistance.slow.init("slow")
        corner_model.resistance.slow.slow.typ.typ = model[1]

    for node, timing in node_model_map.items():
        node.nodeTiming = timing_dict[timing]

    timing_set = set()
    for model in pip_models.values():
        timing_set.add(model)
    timing_dict = {timing: i for i, timing in enumerate(timing_set)}
    dev.init("pipTimings", len(timing_dict))
    for model, i in timing_dict.items():
        pipTiming = dev.pipTimings[i]
        corner_model = pipTiming.internalCapacitance
        corner_model.slow.init("slow")
        corner_model.slow.slow.typ.typ = 0
        corner_model = pipTiming.outputCapacitance
        corner_model.slow.init("slow")
        corner_model.slow.slow.typ.typ = 0
        corner_model = pipTiming.inputCapacitance
        corner_model.slow.init("slow")
        corner_model.slow.slow.typ.typ = model[0] * 1e-9
        corner_model = pipTiming.outputResistance
        corner_model.slow.init("slow")
        corner_model.slow.slow.typ.typ = model[1] * 1e-6
        corner_model = pipTiming.internalDelay
        for i, delay in enumerate(list(model[2])):
            delay = float(delay) * 1e-9
            attr1 = "fast" if i < 2 else "slow"
            attr2 = "min" if i % 2 == 0 else "max"
            v = getattr(corner_model, attr1)
            if v.which() != attr1:
                v.init(attr1)
            v = getattr(v, attr1)
            v = getattr(v, attr2)
            setattr(v, attr2, delay)

    for pip, timing in pip_models.items():
        pip.timing = timing_dict[timing]

    with open(args.patched_device, "wb") as fp:
        write_capnp_file(dev, fp)

if __name__ == "__main__":
    main()
