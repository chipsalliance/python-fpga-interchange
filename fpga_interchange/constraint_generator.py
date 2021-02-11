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


class ConstraintPrototype():
    def __init__(self):
        self.tags = {}
        self.bel_cell_constraints = {}

    def add_tag(self, tag_prefix, tag):
        """ Add a uniquely named tag (and its prefix) to this prototype. """
        assert tag_prefix not in self.tags
        self.tags[tag_prefix] = tag

    def add_cell_placement_constraint(self, cell_type, site_index, site_type,
                                      bel, tag, constraint):
        """ Add a constraint that is applied when a cell is placed.

        The way to read this function:
         - When a cell of type <cell_type> is placed at <bel_index>, apply
           <constraint> to <tag>.
         - When a cell of type <cell_type> is removed from <bel_index>, remove
           <constraint> to <tag>.

        """
        assert tag in self.tags, tag

        key = cell_type, site_index, site_type, bel

        if key not in self.bel_cell_constraints:
            self.bel_cell_constraints[key] = []

        self.bel_cell_constraints[key].append((tag, constraint))
