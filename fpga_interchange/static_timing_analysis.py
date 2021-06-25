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

import argparse

from fpga_interchange.interchange_capnp import Interchange

SECOND_CHOICE = {'slow': 'fast', 'fast': 'slow'}

ALL_POSSIBLE_VALUES = ['min', 'typ', 'max']


class TimingAnalyzer():
    def __init__(self, schema_path, netlist_path, device_path):
        interchange = Interchange(schema_path)
        with open(device_path, "rb") as device_file:
            self.device = interchange.read_device_resources_raw(device_file)
        with open(netlist_path, "rb") as netlist:
            self.phy_netlist = interchange.read_physical_netlist_raw(netlist)

        self.timing_to_all_ends = {}

        # mapping form physical netlist strList to device strList
        self.net_dev_string_map = {}

        # mappig from tile name and wire name to node_id
        self.node_map = {}
        # mapping from node_id to node
        self.node_id_map = {}
        # mapping from wire in node to list of pips connected to node
        self.node_pip_map = {}
        # mapping from (tile,wire0,wire1) to pip
        self.pip_map = {}
        # mapping from tile name to tile type
        self.site_map = {}
        # mapping from site name to site type
        self.tile_map = {}
        # mappinf from (siteType, bel) to bel delays
        self.bel_delays = {}

    def create_net_string_to_dev_string_map(self):
        dev_string = {}
        for i, s in enumerate(self.device.strList):
            dev_string[s] = i
        net_string = []
        for i, s in enumerate(self.phy_netlist.strList):
            net_string.append((s, i))
        for t in net_string:
            if t[0] in dev_string:
                self.net_dev_string_map[t[1]] = dev_string[t[0]]
            else:
                self.net_dev_string_map[t[1]] = None

    def create_wire_to_node_map(self):
        for i, node in enumerate(self.device.nodes):
            for wire in node.wires:
                wire_data = self.device.wires[wire]
                self.node_map[(wire_data.tile, wire_data.wire)] = i
                self.node_id_map[i] = node

    def create_node_to_pip_map(self):
        wire_to_id_map = {}
        wire_id_to_pip = {}
        for i, tileType in enumerate(self.device.tileTypeList):
            for j, wire in enumerate(tileType.wires):
                wire_to_id_map[(i, wire)] = j
                wire_id_to_pip[(i, j)] = []
            for pip in tileType.pips:
                wire_id_to_pip[(i, pip.wire0)].append((pip, True))
                wire_id_to_pip[(i, pip.wire1)].append((pip, False))

        for i, node in enumerate(self.device.nodes):
            key = (node.wires, node.nodeTiming)
            self.node_pip_map[i] = []
            for wire in node.wires:
                wire_data = self.device.wires[wire]
                tile = wire_data.tile
                tile_type = self.tile_map[tile]
                wire_id = wire_to_id_map[(tile_type, wire_data.wire)]
                self.node_pip_map[i] += wire_id_to_pip[(tile_type, wire_id)]

    def create_wires_to_pip_map(self):
        for i, tileType in enumerate(self.device.tileTypeList):
            for pip in tileType.pips:
                wire0 = tileType.wires[pip.wire0]
                wire1 = tileType.wires[pip.wire1]
                self.pip_map[(i, wire0, wire1)] = pip

    def create_site_and_tile_map(self):
        for tile in self.device.tileList:
            self.tile_map[tile.name] = tile.type
            for site in tile.sites:
                t = self.device.tileTypeList[tile.type].siteTypes[
                    site.type].primaryType
                self.site_map[site.name] = t

    def create_PinDelay_map(self):
        for cell in self.device.cellBelMap:
            if len(cell.pinsDelay) == 0:
                continue
            for commonpin in cell.commonPins:
                for site in commonpin.siteTypes:
                    for bel in site.bels:
                        self.bel_delays[(site.siteType, bel)] = cell.pinsDelay

    def net_name(self, net):
        return self.phy_netlist.strList[net.name]

    def traverse_net(self, net):

        ends_array = []

        def get_value_from_model(model, prefered_sub_model, prefered_value):
            prefered = getattr(model, prefered_sub_model)
            if prefered.which() == prefered_sub_model:
                prefered = getattr(prefered, prefered_sub_model)
                prefered_v = getattr(prefered, prefered_value)
                if prefered_v.which() == prefered_value:
                    return getattr(prefered_v, prefered_value)
                for value in ALL_POSSIBLE_VALUES:
                    if getattr(prefered, value) == value:
                        return getattr(getattr(prefered, value), value)
            else:
                prefered = getattr(
                    getattr(model, SECOND_CHOICE[prefered_sub_model]),
                    SECOND_CHOICE[prefered_sub_model])
                for value in ALL_POSSIBLE_VALUES:
                    if getattr(prefered, value) == value:
                        return getattr(getattr(prefered, value), value)

        def get_largest_delay(delays, dType, wire, first_wire=True):
            if len(delays) == 0:
                return 0
            temp_delay = 0
            for delay in delays:
                pin = delay.firstPin.pin if first_wire else delay.secondPin.pin
                if pin == self.net_dev_string_map[
                        wire] and dType == delay.pinsDelayType:
                    temp_delay = max(
                        temp_delay,
                        get_value_from_model(delay.cornerModel, 'slow', 'typ'))
            return temp_delay

        # This calculates delay due to connected pips, even if they are not active.
        def get_pips_delay(pip_list, resistance):
            delay = 0
            for pip in pip_list:
                pip_timing = self.device.pipTimings[pip[0].timing]
                if pip[1]:
                    delay += get_value_from_model(pip_timing.inputCapacitance,
                                                  'slow',
                                                  'typ') * resistance * 0.5
                else:
                    delay += get_value_from_model(
                        pip_timing.outputCapacitance, 'slow',
                        'typ') * (resistance + get_value_from_model(
                            pip_timing.outputResistance, 'slow', 'typ')) * 0.5
            return delay

        def dfs_traverse(vertex, resistance, delay, in_site):
            which = vertex.routeSegment.which()
            temp_delay = 0
            return_value = delay
            last = len(vertex.branches) == 0
            if which == "belPin":
                t = self.site_map[self.net_dev_string_map[vertex.routeSegment.
                                                          belPin.site]]
                pin = self.net_dev_string_map[vertex.routeSegment.belPin.pin]
                site = self.net_dev_string_map[vertex.routeSegment.belPin.site]
                bel = self.net_dev_string_map[vertex.routeSegment.belPin.bel]
                key = (self.device.siteTypeList[t].name,
                       self.net_dev_string_map[vertex.routeSegment.belPin.bel])
                if key in self.bel_delays.keys():
                    delays = self.bel_delays[key]
                    if not last:
                        temp_delay = get_largest_delay(
                            delays, "comb", vertex.routeSegment.belPin.pin)
                    else:
                        temp_delay = get_largest_delay(
                            delays, "setup", vertex.routeSegment.belPin.pin)
                        return_value += temp_delay
            elif which == "sitePin":
                in_site = True
            elif which == "pip":
                tile = self.net_dev_string_map[vertex.routeSegment.pip.tile]
                tile_type = self.tile_map[tile]
                wire0 = self.net_dev_string_map[vertex.routeSegment.pip.wire0]
                wire1 = self.net_dev_string_map[vertex.routeSegment.pip.wire1]

                # Calculate delay from slice to tile
                if in_site:
                    node_id = self.node_map[(tile, wire0)]
                    node = self.node_id_map[node_id]
                    node_model = self.device.nodeTimings[node.nodeTiming]
                    node_resistance = get_value_from_model(
                        node_model.resistance, 'slow', 'typ')
                    node_capacitance = get_value_from_model(
                        node_model.capacitance, 'slow', 'typ')
                    resistance += node_resistance
                    delay += resistance * (node_capacitance) * 0.5
                    delay += get_pips_delay(self.node_pip_map[node_id],
                                            resistance)

                # delay on PIP
                pip = self.pip_map[(self.tile_map[tile], wire0, wire1)]
                pip_timing = self.device.pipTimings[pip.timing]

                if pip.buffered21 and vertex.routeSegment.pip.forward or\
                   pip.buffered20 and not vertex.routeSegment.pip.forward:
                    delay += resistance * get_value_from_model(
                        pip_timing.internalCapacitance, 'slow', 'typ')

                delay += get_value_from_model(pip_timing.internalDelay, 'slow',
                                              'typ')
                if pip.buffered21 and vertex.routeSegment.pip.forward or\
                   pip.buffered20 and not vertex.routeSegment.pip.forward:
                    resistance = get_value_from_model(
                        pip_timing.outputResistance, 'slow', 'typ')
                else:
                    resistance += get_value_from_model(
                        pip_timing.outputResistance, 'slow', 'typ')

                delay += get_value_from_model(pip_timing.outputCapacitance,
                                              'slow', 'typ') * resistance * 0.5

                # Calculate delay for next node
                node_id = self.node_map[(tile, wire1)]
                node = self.node_id_map[node_id]
                node_model = self.device.nodeTimings[node.nodeTiming]
                node_resistance = get_value_from_model(node_model.resistance,
                                                       'slow', 'typ')
                node_capacitance = get_value_from_model(
                    node_model.capacitance, 'slow', 'typ')
                resistance += node_resistance
                delay += resistance * (node_capacitance) * 0.5
                delay += get_pips_delay(self.node_pip_map[node_id], resistance)
                # Remove delay of PIP we are in
                delay -= get_value_from_model(pip_timing.outputCapacitance, 'slow', 'typ') *\
                        (resistance + get_value_from_model(
                            pip_timing.outputResistance,
                            'slow',
                            'typ')
                        ) * 0.5

            elif which == "sitePIP":
                t = self.site_map[self.net_dev_string_map[vertex.routeSegment.
                                                          sitePIP.site]]
                delays = self.bel_delays[(
                    self.device.siteTypeList[t].name,
                    self.net_dev_string_map[vertex.routeSegment.sitePIP.bel])]
                temp_delay = get_largest_delay(delays, "comb",
                                               vertex.routeSegment.sitePIP.pin)
            for branch in vertex.branches:
                return_value = max(
                    dfs_traverse(branch, resistance, delay + temp_delay,
                                 in_site), return_value)
            if last:
                ends_array.append((site, bel, pin, delay))
            return return_value

        self.timing_to_all_ends[net] = []

        return_value = 0
        for source in net.sources:
            ends_array = []
            which = source.routeSegment.which()
            if which == "belPin":
                t = self.site_map[self.net_dev_string_map[source.routeSegment.
                                                          belPin.site]]
                key = (self.device.siteTypeList[t].name,
                       self.net_dev_string_map[source.routeSegment.belPin.bel])
                temp_delay = 0
                if key in self.bel_delays.keys():
                    delays = self.bel_delays[key]
                    temp_delay = get_largest_delay(
                        delays, "clk2q", source.routeSegment.belPin.pin)
                for branch in source.branches:
                    return_value = max(
                        dfs_traverse(branch, 0, temp_delay, False),
                        return_value)
            else:
                raise
            self.timing_to_all_ends[net].append((source.routeSegment.belPin,
                                                 ends_array))
        return return_value


# ============================================================================


def main():

    parser = argparse.ArgumentParser(
        description="Performs static timing analysis")
    parser.add_argument(
        "--schema_dir",
        required=True,
        help="Path to FPGA interchange capnp schema files")
    parser.add_argument(
        "--physical_netlist",
        required=True,
        help="Path to physical netlist for timing analysis")
    parser.add_argument("--device", required=True, help="Path to device capnp")
    parser.add_argument(
        "--detail",
        action='store_true',
        help="If set analyze will print timing to Net ends")

    args = parser.parse_args()
    analyzer = TimingAnalyzer(args.schema_dir, args.physical_netlist,
                              args.device)
    analyzer.create_net_string_to_dev_string_map()
    analyzer.create_wire_to_node_map()
    analyzer.create_wires_to_pip_map()
    analyzer.create_site_and_tile_map()
    analyzer.create_node_to_pip_map()
    analyzer.create_PinDelay_map()
    array = []
    for net in analyzer.phy_netlist.physNets:
        array.append(net)
    for i, net in enumerate(array):
        if net.type == "signal":
            print(
                f"Net {analyzer.net_name(net)} max time delay: {analyzer.traverse_net(net) * 1e9} ns"
            )
            if args.detail:
                print("\tDetail report:")
                for source, ends in analyzer.timing_to_all_ends[net]:
                    print(
                        f"\t\t(Source) Site {analyzer.phy_netlist.strList[source.site]}, BEL {analyzer.phy_netlist.strList[source.bel]}, BELpin{analyzer.phy_netlist.strList[source.pin]}"
                    )
                    for end in ends:
                        print(
                            f"\t\t\t -> (Sink) Site {analyzer.device.strList[end[0]]}, BEL {analyzer.device.strList[end[1]]}, BELpin {analyzer.device.strList[end[2]]}"
                        )
                        print(f"\t\t\t\t time delay {end[3]} ns")


# =============================================================================

if __name__ == "__main__":
    main()
