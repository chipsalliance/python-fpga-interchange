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

def create_bel_pin_to_index_map(device):
    bel_pin_to_index = dict()

    for i, site in enumerate(device.siteTypeList):
        site_type = device.strList[site.name]
        bel_pin_to_index[site_type] = dict()

        for j, bel_pin in enumerate(site.belPins):
            pin = device.strList[bel_pin.name]
            bel = device.strList[bel_pin.bel]

            if bel not in bel_pin_to_index[site_type]:
                bel_pin_to_index[site_type][bel] = dict()
            bel_pin_to_index[site_type][bel][pin] = j

    return bel_pin_to_index

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

def populate_pin_delays(string_map, cell_bel_mapping, timings):
    """
    Populates pin delays for the given cell bel pin map.
    """

    def populate_pin(pin, data, key):
        """
        Fills in a PinDelay struct
        """
        bel_pin = data[key + "_pin"]
        edge = data[key + "_pin_edge"]

        pin.pin = bel_pin
        if edge is not None:
            assert edge in ["posedge", "negedge"], edge
            if edge == "posedge":
                pin.clockEdge = "rise"
            if edge == "negedge":
                pin.clockEdge = "fall"

    # Maps path type from SDF to the FPGA interchange schema
    # "clk2q" is detected separately as it is not a separate type in SDF
    TYPE_MAP = {
        "iopath": "comb",
        "setup": "setup",
        "hold": "hold",
        "recovery": "setup",
        "removal": "hold",
    }

    pins_delay = cell_bel_mapping.init("pinsDelay", len(timings))
    for j, timing in enumerate(timings):
        entry = pins_delay[j]

        # Site
        entry.site = string_map[timing["site"]]

        # Type
        assert timing["type"] in TYPE_MAP, timing["type"]
        typ = TYPE_MAP[timing["type"]]
        if typ == "comb" and timing["from_pin_edge"] is not None:
            typ = "clk2q"

        entry.pinsDelayType = typ

        # From
        pin = entry.init("firstPin")
        populate_pin(pin, timing, "from")

        # To
        pin = entry.init("secondPin")
        populate_pin(pin, timing, "to")

        # Timing data
        entry.init("cornerModel")
        corner_model = entry.cornerModel

        delays_slow = timing["delays"]["slow"]
        delays_fast = timing["delays"]["fast"]
        populate_corner_model(corner_model,
            delays_fast["min"], delays_fast["typ"], delays_fast["max"],
            delays_slow["min"], delays_slow["typ"], delays_slow["max"]
        )


def collect_pins_delay(device, bel_pin_to_index_map, cell, pin_map, cell_timing_data):
    """
    Collects timing data for the given cell type and cell bel pin mapping.
    Matches the SDF data against device resources data. Converts BEL pin names
    to their indices.
    """

    pins_delay = dict()

    for entry in pin_map.siteTypes:
        site = device.strList[entry.siteType]

        if site not in cell_timing_data:
            print("WARNING: no timing data for site '{}'".format(site))
            continue

        for bel_i in entry.bels:
            bel = device.strList[bel_i]

            if bel not in cell_timing_data[site]:
                print("WARNING: no timing data for site/bel '{}/{}'".format(site, bel))
                continue

            # Get timings for the specific cell. If not found then
            # look for data for "any" cell.
            timings = cell_timing_data[site][bel].get(cell, None)
            if timings is None:
                timings = cell_timing_data[site][bel].get(None, None)

            if timings is None:
                print("WARNING: not timing data for cell '{}' at site/bel '{}/{}'".format(cell, site, bel))
                continue

            # Translate the timing data
            print(" ", "@ {}/{}".format(site, bel))

            if site not in pins_delay:
                pins_delay[site] = dict()

            for path_name, path in timings.items():

                pin_1 = bel_pin_to_index_map[site][bel].get(path["from_pin"], None)
                pin_2 = bel_pin_to_index_map[site][bel].get(path["to_pin"],   None)
                if pin_1 is None or pin_2 is None:
                    if pin_1 is None:
                        print("WARNING: unknown bel pin '{}.{}'".format(bel, path["from_pin"]))
                    if pin_2 is None:
                        print("WARNING: unknown bel pin '{}.{}'".format(bel, path["to_pin"]))
                    continue

                # Take the slow and fast corner
                delays = path["delay_paths"]
                corner = dict()
                for key in ["slow", "fast"]:
                    if key in delays:
                        corner[key] = {
                            "min": delays[key]["min"],
                            "typ": delays[key]["avg"],
                            "max": delays[key]["max"],
                        }

                # If no slow or fast data was found but there is "nominal" then
                # use it for both.
                if not corner and "nominal" in delays:
                    for key in ["slow", "fast"]:
                        corner[key] = {
                            "min": delays["nominal"]["min"],
                            "typ": delays["nominal"]["avg"],
                            "max": delays["nominal"]["max"],
                        }

                if not corner:
                    print("WARNING: no timing data for path '{}'".format(path_name))
                    continue

                if bel not in pins_delay[site]:
                    pins_delay[site][bel] = list()

                data = {
                    "from_pin": pin_1,
                    "from_pin_edge": path.get("from_pin_edge", None),
                    "to_pin": pin_2,
                    "to_pin_edge": path.get("to_pin_edge", None),
                    "type": path["type"],
                    "delays": corner
                }
                pins_delay[site][bel].append(data)

                # DEBUG
                print("   ", path_name)

            # No valid data could be translated, delete the site entry
            if not pins_delay[site]:
                del pins_delay[site]

    # Flatten entries
    flat_pins_delay = []
    for site, bels in pins_delay.items():
        for bel, timings in bels.items():
            for data in timings:
                entry = {
                    "site": site,
                    "bel": bel
                }
                entry.update(data)
                flat_pins_delay.append(entry)

    return flat_pins_delay


def main():
    parser = argparse.ArgumentParser(
        description="Add timing information to Device")

    parser.add_argument("--schema_dir", required=True)
    parser.add_argument("--timing_dir", required=True)
    parser.add_argument("--timing_map", required=True)
    parser.add_argument("--family", required=True)
    parser.add_argument("device")
    parser.add_argument("patched_device")

    args = parser.parse_args()

    print("Loading device resources...")
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
    bel_pin_to_index_map = create_bel_pin_to_index_map(dev)

    tile_type_name_to_number = {}
    for i, tileType in enumerate(dev.tileTypeList):
        name = dev.strList[tileType.name]
        tile_type_name_to_number[name] = i

    pip_models = {}

    family_map = {"xc7": prjxray_db_reader}

    print("Loading timing data...")
    timing_dir = args.timing_dir
    timing_reader = family_map[args.family](timing_dir, args.timing_map)
    timing_data, cell_timing_data = timing_reader.extract_data()

    print("Patching device resources with timing data...")

    for i, mapping in enumerate(dev.cellBelMap):
        cell = dev.strList[mapping.cell]
        print("", cell)

        # Common pin maps
        for pin_map in mapping.commonPins:
            timings = collect_pins_delay(dev, bel_pin_to_index_map, cell, pin_map, cell_timing_data)
            populate_pin_delays(string_map, mapping, timings)
                
        # Parameter pin maps
        # TODO

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

    print("Writing device resources...")
    with open(args.patched_device, "wb") as fp:
        write_capnp_file(dev, fp)


if __name__ == "__main__":
    main()
