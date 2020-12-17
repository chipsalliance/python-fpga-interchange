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
    if parser is None:
        parser = capnp.lib.capnp._global_schema_parser

    return parser.modules_by_id[capnp_id]
