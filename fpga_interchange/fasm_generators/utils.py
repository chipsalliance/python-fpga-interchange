#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2021  The F4PGA Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC

from fpga_interchange.parameter_definitions import ParameterDefinition


def format_feature_value(bits, start_bit=0):
    """
    Formats a FASM feature value assignment according to the given bits
    as a string or any iterable yeilding "0" and "1". The iterable must return
    bits starting from LSB and ending on MSB. The yieled bit count determines
    the FASM feature assignment width - there is no padding. Optionally the
    start_bit parameter can be used for offset.
    """
    bits = list(bits)

    count = len(bits)
    value = "".join(bits[::-1])

    if count == 1:
        bitrange = "[{}]".format(start_bit)
    elif count > 1:
        bitrange = "[{}:{}]".format(count - 1 + start_bit, start_bit)
    else:
        assert False, count

    return "{}={}'b{}".format(bitrange, count, value)


def get_cell_integer_param(device_resources,
                           cell_data,
                           name,
                           force_format=None):
    """
    Retrieves definition and decodes value of an integer cell parameter. The
    function can optionally force a specific encoding format if needed.
    """

    # Get the parameter definition to determine its type
    param = device_resources.get_parameter_definition(cell_data.cell_type,
                                                      name)

    # Force the format if requested by substituting the paraameter
    # definition object.
    if not param.is_integer_like() and force_format is not None:
        if force_format != param.string_format:
            param = ParameterDefinition(
                name=name,
                string_format=force_format,
                default_value=cell_data.attributes[name])

    # Decode
    return param.decode_integer(cell_data.attributes[name])
