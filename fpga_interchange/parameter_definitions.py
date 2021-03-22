#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2020  The SymbiFlow Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
from enum import Enum
import re


class ParameterFormat(Enum):
    STRING = 0
    BOOLEAN = 1
    INTEGER = 2
    FLOATING_POINT = 3
    VERILOG_BINARY = 4
    VERILOG_HEX = 5
    C_BINARY = 6
    C_HEX = 7


# 0/1/256
INTEGER_RE = re.compile(r'[0-9]+$')

# 0.0
FLOATING_POINT_RE = re.compile(r'([0-9]*)\.([0-9]*)$')

# 1'b0
VERILOG_BINARY_RE = re.compile(r"([1-9][0-9]*)'b([01]+)$")

# 1'h0
VERILOG_HEX_RE = re.compile(r"([1-9][0-9]*)'h([0-9a-fA-F]+)$")

# 0b10
C_BINARY_RE = re.compile(r"0b([01]+)$")

# 0xF
C_HEX_RE = re.compile(r"0x([0-9a-fA-F]+)$")


def is_parameter_formatted(format_type, str_value):
    """ Is parameter formatted per the format_type specified?

    >>> is_parameter_formatted(ParameterFormat.STRING, "")
    True
    >>> is_parameter_formatted(ParameterFormat.BOOLEAN, "TRUE")
    True
    >>> is_parameter_formatted(ParameterFormat.BOOLEAN, "FALSE")
    True
    >>> is_parameter_formatted(ParameterFormat.BOOLEAN, "1")
    True
    >>> is_parameter_formatted(ParameterFormat.BOOLEAN, "0")
    True
    >>> is_parameter_formatted(ParameterFormat.BOOLEAN, "2")
    False
    >>> is_parameter_formatted(ParameterFormat.INTEGER, "0")
    True
    >>> is_parameter_formatted(ParameterFormat.INTEGER, "1")
    True
    >>> is_parameter_formatted(ParameterFormat.INTEGER, "a")
    False
    >>> is_parameter_formatted(ParameterFormat.INTEGER, "01")
    False
    >>> is_parameter_formatted(ParameterFormat.FLOATING_POINT, "1.")
    True
    >>> is_parameter_formatted(ParameterFormat.FLOATING_POINT, "0.")
    True
    >>> is_parameter_formatted(ParameterFormat.FLOATING_POINT, "1.0")
    True
    >>> is_parameter_formatted(ParameterFormat.FLOATING_POINT, "0.0")
    True
    >>> is_parameter_formatted(ParameterFormat.FLOATING_POINT, ".1")
    True
    >>> is_parameter_formatted(ParameterFormat.FLOATING_POINT, ".0")
    True
    >>> is_parameter_formatted(ParameterFormat.FLOATING_POINT, ".")
    False
    >>> is_parameter_formatted(ParameterFormat.VERILOG_BINARY, "1'b1")
    True
    >>> is_parameter_formatted(ParameterFormat.VERILOG_BINARY, "1'b11")
    False
    >>> is_parameter_formatted(ParameterFormat.VERILOG_HEX, "4'hF")
    True
    >>> is_parameter_formatted(ParameterFormat.VERILOG_HEX, "5'h1F")
    True
    >>> is_parameter_formatted(ParameterFormat.VERILOG_HEX, "4'h1F")
    False
    >>> is_parameter_formatted(ParameterFormat.C_BINARY, "0b011")
    True
    >>> is_parameter_formatted(ParameterFormat.C_BINARY, "0b012")
    False
    >>> is_parameter_formatted(ParameterFormat.C_HEX, "0xF")
    True
    >>> is_parameter_formatted(ParameterFormat.C_HEX, "F")
    False

    """
    if format_type == ParameterFormat.STRING:
        # All strings are accepted!
        return True
    elif format_type == ParameterFormat.BOOLEAN:
        return str_value == "TRUE" or str_value == "FALSE" or str_value == "0" or str_value == "1"
    elif format_type == ParameterFormat.INTEGER:
        m = INTEGER_RE.match(str_value)
        if m is None:
            return False

        if len(str_value) > 1 and str_value[0] == '0':
            # No leading zeros.
            return False

        return True
    elif format_type == ParameterFormat.FLOATING_POINT:
        m = FLOATING_POINT_RE.match(str_value)
        if m is None:
            return False

        if m.group(1) == '' and m.group(2) == '':
            # '.' is not valid, but 1. and .0 are valid.
            return False
        else:
            return True
    elif format_type == ParameterFormat.VERILOG_BINARY:
        m = VERILOG_BINARY_RE.match(str_value)
        if m is None:
            return False

        width = int(m.group(1))
        return width >= len(m.group(2))
    elif format_type == ParameterFormat.VERILOG_HEX:
        m = VERILOG_HEX_RE.match(str_value)
        if m is None:
            return False

        width = int(m.group(1))

        rem = width % 4
        if rem != 0:
            # Round up to nearest multiple of 4
            width += (4 - rem)

        return width >= len(m.group(2)) * 4
    elif format_type == ParameterFormat.C_BINARY:
        m = C_BINARY_RE.match(str_value)
        return m is not None
    elif format_type == ParameterFormat.C_HEX:
        m = C_HEX_RE.match(str_value)
        return m is not None
    else:
        raise RuntimeError("Unknown format_type {}".format(format_type))


class ParameterDefinition():
    """ Definition for a parameter in the logical netlist.

    name (str) - Name of the parameter
    string_format (ParameterFormat) - When expressed as a string, how should
        this parameter be formatted?
    default_value (str) - What is the default value of this parameter?

    """

    def __init__(self, name, string_format, default_value):
        self.name = name
        self.string_format = string_format
        self.default_value = default_value
        self.width = None

        assert is_parameter_formatted(self.string_format, self.default_value)

        if self.string_format == ParameterFormat.VERILOG_BINARY:
            m = VERILOG_BINARY_RE.match(self.default_value)
            assert m is not None
            self.width = int(m.group(1))

        if self.string_format == ParameterFormat.VERILOG_HEX:
            m = VERILOG_HEX_RE.match(self.default_value)
            assert m is not None
            self.width = int(m.group(1))

    def is_integer_like(self):
        return self.string_format in [
            ParameterFormat.BOOLEAN,
            ParameterFormat.INTEGER,
            ParameterFormat.VERILOG_BINARY,
            ParameterFormat.VERILOG_HEX,
            ParameterFormat.C_BINARY,
            ParameterFormat.C_HEX,
        ]

    def encode_integer(self, int_value):
        if self.string_format == ParameterFormat.BOOLEAN:
            if int_value == 0:
                return 'FALSE'
            elif int_value == 1:
                return 'TRUE'
            else:
                raise ValueError(
                    'Invalid boolean int value {}'.format(int_value))
        elif self.string_format == ParameterFormat.INTEGER:
            return '{}'.format(int_value)
        elif self.string_format == ParameterFormat.VERILOG_BINARY:
            assert self.width is not None
            assert int_value >= 0, int_value
            assert int_value <= (2**self.width), (self.width, int_value)
            return "{}'b{:b}".format(self.width, int_value)
        elif self.string_format == ParameterFormat.VERILOG_HEX:
            assert self.width is not None
            assert int_value >= 0, int_value
            assert int_value <= (2**self.width), (self.width, int_value)
            return "{}'h{:X}".format(self.width, int_value)
        elif self.string_format == ParameterFormat.C_BINARY:
            return '0b{:b}'.format(int_value)
        elif self.string_format == ParameterFormat.C_HEX:
            return '0x{:X}'.format(int_value)
