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

from fpga_interchange.constraints.model import BelMatcher


class PlacementOracle():
    """ Placement oracle returns a set of matchers for a cell type. """

    def __init__(self):
        self.cell_types = {}

    def add_cell_matcher(self, cell_type, site_type, bel):
        if cell_type not in self.cell_types:
            self.cell_types[cell_type] = []

        self.cell_types[cell_type].append(BelMatcher(site_type, bel))

    def matchers_for_cell(self, cell_type):
        """ Returns list of matchers for a cell type. """
        if cell_type not in self.cell_types:
            assert False, 'Unsupported cell {}'.format(cell_type)

        return self.cell_types[cell_type]

    def add_sites_from_device(self, device):
        self.cell_types = {}

        for cell_bel in device.yield_cell_bel_mappings():
            for site_type, bel in cell_bel.site_types_and_bels:
                self.add_cell_matcher(
                    str(cell_bel.cell), str(site_type), str(bel))
