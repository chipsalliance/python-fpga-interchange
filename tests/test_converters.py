#/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2020  The SymbiFlow Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC

import os
import unittest
import json
import yaml
from yaml import CSafeLoader as SafeLoader, CDumper as Dumper

import fpga_interchange.converters
from fpga_interchange.capnp_utils import get_module_from_id
from fpga_interchange.interchange_capnp import Interchange
from example_netlist import example_logical_netlist, example_physical_netlist


class TestConverterRoundTrip(unittest.TestCase):
    def round_trip_json(self, in_message):
        value = fpga_interchange.converters.to_json(in_message)
        json_string = json.dumps(value)

        value_out = json.loads(json_string)
        message = get_module_from_id(in_message.schema.node.id).new_message()
        fpga_interchange.converters.from_json(message, value_out)
        value2 = fpga_interchange.converters.to_json(message)
        json_string2 = json.dumps(value2)

        value2_out = json.loads(json_string2)

        self.assertTrue(value_out == value2_out)

    def round_trip_yaml(self, in_message):
        value = fpga_interchange.converters.to_yaml(in_message)
        yaml_string = yaml.dump(value, Dumper=Dumper)

        value_out = yaml.load(yaml_string, Loader=SafeLoader)
        message = get_module_from_id(in_message.schema.node.id).new_message()
        fpga_interchange.converters.from_yaml(message, value_out)
        value2 = fpga_interchange.converters.to_yaml(message)
        yaml_string2 = yaml.dump(value2, Dumper=Dumper)

        value2_out = yaml.load(yaml_string2, Loader=SafeLoader)

        self.assertTrue(value_out == value2_out)

    def test_logical_netlist_json(self):
        logical_netlist = example_logical_netlist()

        interchange = Interchange(
            schema_directory=os.environ['INTERCHANGE_SCHEMA_PATH'])
        netlist_capnp = logical_netlist.convert_to_capnp(interchange)

        self.round_trip_json(netlist_capnp)

    def test_physical_netlist_json(self):
        phys_netlist = example_physical_netlist()

        interchange = Interchange(
            schema_directory=os.environ['INTERCHANGE_SCHEMA_PATH'])
        netlist_capnp = phys_netlist.convert_to_capnp(interchange)

        self.round_trip_json(netlist_capnp)

    def test_device_json(self):
        phys_netlist = example_physical_netlist()

        interchange = Interchange(
            schema_directory=os.environ['INTERCHANGE_SCHEMA_PATH'])

        with open(
                os.path.join(os.environ['DEVICE_RESOURCE_PATH'],
                             phys_netlist.part + '.device'), 'rb') as f:
            dev_message = interchange.read_device_resources_raw(f)

        self.round_trip_json(dev_message)

    def test_logical_netlist_yaml(self):
        logical_netlist = example_logical_netlist()

        interchange = Interchange(
            schema_directory=os.environ['INTERCHANGE_SCHEMA_PATH'])
        netlist_capnp = logical_netlist.convert_to_capnp(interchange)

        self.round_trip_yaml(netlist_capnp)

    def test_physical_netlist_yaml(self):
        phys_netlist = example_physical_netlist()

        interchange = Interchange(
            schema_directory=os.environ['INTERCHANGE_SCHEMA_PATH'])
        netlist_capnp = phys_netlist.convert_to_capnp(interchange)

        self.round_trip_yaml(netlist_capnp)

    def test_device_yaml(self):
        phys_netlist = example_physical_netlist()

        interchange = Interchange(
            schema_directory=os.environ['INTERCHANGE_SCHEMA_PATH'])

        with open(
                os.path.join(os.environ['DEVICE_RESOURCE_PATH'],
                             phys_netlist.part + '.device'), 'rb') as f:
            dev_message = interchange.read_device_resources_raw(f)

        self.round_trip_yaml(dev_message)
