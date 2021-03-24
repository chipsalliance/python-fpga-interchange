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
import capnp.lib.capnp


def get_module_from_id(capnp_id, parser=None):
    """ Return the capnp module based on the capnp node id.

    This is useful to determine the schema of a node within a capnp tree.

    The parser argument is optional, because in most circumstances the pycapnp
    _global_schema_parser is used.  In the event that this parser was not used,
    the parser must be provided.  This case should be rare.

    """
    if parser is None:
        parser = capnp.lib.capnp._global_schema_parser

    return parser.modules_by_id[capnp_id]
