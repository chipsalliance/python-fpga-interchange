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
from math import log2

from fpga_interchange.chip_info_utils import LutCell, LutBel, LutElement


class LutMapper():
    def __init__(self, device_resources):
        """
        Fills luts definition from the device resources database
        """

        self.site_lut_elements = dict()
        self.lut_cells = dict()

        for site_lut_element in device_resources.device_resource_capnp.lutDefinitions.lutElements:
            site = site_lut_element.site
            self.site_lut_elements[site] = list()
            for lut in site_lut_element.luts:
                lut_element = LutElement()
                self.site_lut_elements[site].append(lut_element)

                lut_element.width = lut.width

                for bel in lut.bels:
                    lut_bel = LutBel()
                    lut_element.lut_bels.append(lut_bel)

                    lut_bel.name = bel.name
                    for pin in bel.inputPins:
                        lut_bel.pins.append(pin)

                    lut_bel.out_pin = bel.outputPin

                    assert bel.lowBit < lut.width
                    assert bel.highBit < lut.width

                    lut_bel.low_bit = bel.lowBit
                    lut_bel.high_bit = bel.highBit

        for lut_cell in device_resources.device_resource_capnp.lutDefinitions.lutCells:
            lut = LutCell()
            self.lut_cells[lut_cell.cell] = lut

            lut.name = lut_cell.cell
            for pin in lut_cell.inputPins:
                lut.pins.append(pin)

    def find_lut_bel(self, site_type, bel):
        """
        Returns the LUT Bel definition and the corresponding LUT element given the
        corresponding site_type and bel name
        """
        assert site_type in self.site_lut_elements, site_type
        lut_elements = self.site_lut_elements[site_type]

        for lut_element in lut_elements:
            for lut_bel in lut_element.lut_bels:
                if lut_bel.name == bel:
                    return lut_element, lut_bel

        assert False

    def get_phys_lut_init(self, log_init, lut_element, lut_bel, lut_cell,
                          phys_to_log):
        bitstring_init = "{value:0{digits}b}".format(
            value=log_init, digits=lut_bel.high_bit + 1)

        # Invert the string to have the LSB at the beginning
        logical_lut_init = bitstring_init[::-1]

        physical_lut_init = str()
        for phys_init_index in range(0, lut_element.width):
            log_init_index = 0

            for phys_port_idx in range(0, int(log2(lut_element.width))):
                if not phys_init_index & (1 << phys_port_idx):
                    continue

                log_port = None
                if phys_port_idx < len(lut_bel.pins):
                    log_port = phys_to_log.get(lut_bel.pins[phys_port_idx])

                if log_port is None:
                    continue

                log_port_idx = lut_cell.pins.index(log_port)
                log_init_index |= (1 << log_port_idx)

            physical_lut_init += logical_lut_init[log_init_index]

        # Invert the string to have the MSB at the beginning
        return physical_lut_init[::-1]

    def get_phys_cell_lut_init(self, logical_init_value, cell_data):
        """
        Returns the LUTs physical INIT parameter mapping given the initial logical INIT
        value and the cells' data containing the physical mapping of the input pins.

        It is left to the caller to handle cases of fractured LUTs.
        """

        def physical_to_logical_map(lut_bel, bel_pins):
            """
            Returns the physical pin to logical pin LUTs mapping.
            Unused physical pins are set to None.
            """
            phys_to_log = dict()

            for pin in lut_bel.pins:
                phys_to_log[pin] = None

                for bel_pin in bel_pins:
                    if bel_pin.bel_pin == pin:
                        phys_to_log[pin] = bel_pin.cell_pin
                        break

            return phys_to_log

        cell_type = cell_data.cell_type
        bel = cell_data.bel
        bel_pins = cell_data.bel_pins
        site_type = cell_data.site_type

        lut_element, lut_bel = self.find_lut_bel(site_type, bel)
        phys_to_log = physical_to_logical_map(lut_bel, bel_pins)
        lut_cell = self.lut_cells[cell_type]

        return self.get_phys_lut_init(logical_init_value, lut_element, lut_bel,
                                      lut_cell, phys_to_log)

    def get_phys_wire_lut_init(self,
                               logical_init_value,
                               site_type,
                               cell_type,
                               bel,
                               bel_pin,
                               lut_pin=None):
        """
        Returns the LUTs physical INIT parameter mapping of a LUT-thru wire

        It is left to the caller to handle cases of fructured LUTs.
        """

        lut_element, lut_bel = self.find_lut_bel(site_type, bel)
        lut_cell = self.lut_cells[cell_type]
        phys_to_log = dict((pin, None) for pin in lut_bel.pins)

        if lut_pin == None:
            assert len(lut_cell.pins) == 1, (lut_cell.name, lut_cell.pins)
            phys_to_log[bel_pin] = lut_cell.pins[0]
        else:
            phys_to_log[bel_pin] = lut_pin

        return self.get_phys_lut_init(logical_init_value, lut_element, lut_bel,
                                      lut_cell, phys_to_log)

    def get_const_lut_init(self, const_init_value, site_type, bel):
        """
        Returns the LUTs physical INIT parameter mapping of a wire tied to
        the constant net (GND or VCC).
        """

        lut_element, _ = self.find_lut_bel(site_type, bel)
        width = lut_element.width

        return "".rjust(width, str(const_init_value))
