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

TOP_OF_HEADER = """
/*
 *  nextpnr -- Next Generation Place and Route
 *
 *  Copyright (C) 2021  The SymbiFlow Authors.
 *
 *  Permission to use, copy, modify, and/or distribute this software for any
 *  purpose with or without fee is hereby granted, provided that the above
 *  copyright notice and this permission notice appear in all copies.
 *
 *  THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
 *  WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
 *  MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
 *  ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
 *  WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
 *  ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
 *  OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
 *
 */

#pragma once

#include <cstdint>
#include "log.h"
#include "nextpnr.h"
#include "exclusive_state_groups.h"

NEXTPNR_NAMESPACE_BEGIN
"""

TOP_OF_SOURCE = """
/*
 *  nextpnr -- Next Generation Place and Route
 *
 *  Copyright (C) 2021  The SymbiFlow Authors.
 *
 *  Permission to use, copy, modify, and/or distribute this software for any
 *  purpose with or without fee is hereby granted, provided that the above
 *  copyright notice and this permission notice appear in all copies.
 *
 *  THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
 *  WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
 *  MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
 *  ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
 *  WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
 *  ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
 *  OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
 *
 */

#include <cstdint>
#include "log.h"
#include "nextpnr.h"
#include "exclusive_state_groups.h"
#include "exclusive_state_groups.impl.h"

NEXTPNR_NAMESPACE_BEGIN

"""

BOTTOM_OF_FILE = """
NEXTPNR_NAMESPACE_END
"""


class CppIncrementalExclusiveStateGroup():
    """ The core of the current constraint model is the idea of exclusive
    state groups. Exclusive state groups have the following properties:

    - The group has a set of possible sets.
    - By default no state is selected.
    - In order for the state group to be valid, only 1 state can be selected.
      A state is selected through an "implies" constraint.  Multiple
      "implies" constraint can select the same state.
    - A "requires" constraint is satified if a state group has a particular
      value.  A "requires" constraint cannot change the state of state group
      from unselected to selected.

    """

    def __init__(self, prefix, default, states):
        self.prefix = prefix
        self.states = states

        assert self.default in self.states
        self.default = default

        self.state_to_index = {}

        for idx, state in enumerate(self.states):
            self.state_to_index[state] = idx


class ConstraintPrototype():
    def __init__(self):
        self.tags = {}
        self.bel_cell_constraints = {}

    def add_tag(self, tag_prefix, tag):
        """ Add a uniquely named tag (and its prefix) to this prototype. """
        assert tag_prefix not in self.tags
        self.tags[tag_prefix] = tag

    def add_cell_placement_constraint(self, cell_type, site_index, bel, tag,
                                      constraint):
        """ Add a constraint that is applied when a cell is placed.

        The way to read this function:
         - When a cell of type <cell_type> is placed at <bel_index>, apply
           <constraint> to <tag>.
         - When a cell of type <cell_type> is removed from <bel_index>, remove
           <constraint> to <tag>.

        """
        assert tag in self.tags, tag

        key = cell_type, site_index, bel

        if key not in self.bel_cell_constraints:
            self.bel_cell_constraints[key] = []

        self.bel_cell_constraints[key].append((tag, constraint))


CONSTRAINT_DEFINITION = """
struct Constraints {{
    // Maximum number of states need implement constraints.
    static constexpr size_t kMaxTags = {max_tags};
    static constexpr size_t kMaxStates = {max_states};

    typedef ExclusiveStateGroup<kMaxStates, /*StateType=*/{state_type}, /*CountType=*/{count_type}> TagState;

{prototype_enums}

    Constraints();

    void print_constraint_debug(Context *ctx, ConstraintPrototype prototype, const TagState *tags) const;

    bool isValidBelForCellType(ConstraintPrototype prototype, const TagState *tags, BelId bel, IdString cell_type, bool explain) const;
    bool bindBel(ConstraintPrototype prototype, TagState *tags, BelId bel, IdString cell_type, bool explain);
    void unbindBel(ConstraintPrototype prototype, TagState *tags, BelId bel, IdString cell_type);

    size_t getCellIndex(IdString cell_type);

    std::vector<TagState::Definition> definitions;
}};
"""

CONSTRAINT_IMPLEMENTATION = """
size_t Constraints::getCellIndex(IdString cell_type) {
    int32_t offset = cell_type.index - kFirstCellName;
    NPNR_ASSERT(offset >= 0 && offset < kCellCount);
    return offset;
}

bool Constraints::isValidBelForCellType(ConstraintPrototype prototype,
    const TagState *tags, BelId bel, IdString cell_type, bool explain) const {
    size_t cell_index = getCellIndex(cell_type);

    NPNR_ASSERT(prototype < PROTOTYPE_COUNT);
    if(cell_index >= kCellCounts[prototype]) {
        return false;
    }
    NPNR_ASSERT(bel.index < kBelCounts[prototype]);

    // FIXME: Implement.
    return true;
}

bool Constraints::bindBel(ConstraintPrototype prototype, TagState *tags,
    BelId bel, IdString cell_type, bool explain) {
    size_t cell_index = getCellIndex(cell_type);

    NPNR_ASSERT(prototype < PROTOTYPE_COUNT);
    if(cell_index >= kCellCounts[prototype]) {
        return false;
    }
    NPNR_ASSERT(bel.index < kBelCounts[prototype]);

    // FIXME: Implement.
    return true;
}

void Constraints::unbindBel(ConstraintPrototype prototype, TagState *tags,
    BelId bel, IdString cell_type) {
    size_t cell_index = getCellIndex(cell_type);

    NPNR_ASSERT(prototype < PROTOTYPE_COUNT);
    if(cell_index >= kCellCounts[prototype]) {
        return false;
    }
    NPNR_ASSERT(bel.index < kBelCounts[prototype]);

    // FIXME: Implement.
    return true;
}
"""


class ConstraintGenerator():
    def __init__(self, model):
        self.prototype_names = []
        self.prototype_index = {}
        self.prototypes = {}
        self.model = model

    def add_constraint_prototype(self, prototype):
        assert prototype not in self.prototypes

        data = ConstraintPrototype()
        self.prototype_index[prototype] = len(self.prototype_names)
        self.prototype_names.append(prototype)
        self.prototypes[prototype] = data
        return data

    def get_prototype_index(self, prototype):
        return self.prototype_index[prototype]

    def emit_header(self, f):
        max_tags = 0
        max_states = 0
        for prototype in self.prototypes.values():
            max_tags = max(max_tags, len(prototype.tags))
            for tag in prototype.tags.values():
                max_states = max(max_states, len(tag.states))

        f.write(TOP_OF_HEADER)
        prototype_enums = "    enum ConstraintPrototype {\n"
        for idx, prototype in enumerate(self.prototype_names):
            prototype_enums += "        PROTOTYPE_{} = {},\n".format(
                prototype, idx)
        prototype_enums += "        PROTOTYPE_COUNT = {}\n".format(
            len(self.prototypes))
        prototype_enums += "    };\n"

        if max_states <= 127:
            state_type = 'int8_t'
        elif max_states <= 32767:
            state_type = 'int16_t'

        # FIXME: This should be large enough to never overflow if all BELs are
        # occupied.
        count_type = 'uint8_t'

        f.write(
            CONSTRAINT_DEFINITION.format(
                max_tags=max_tags,
                max_states=max_states,
                state_type=state_type,
                count_type=count_type,
                prototype_enums=prototype_enums))
        f.write(BOTTOM_OF_FILE)

    def emit_source(self, f, cell_names, constids):
        f.write(TOP_OF_SOURCE)

        min_cell = min(
            constids.get_index(cell_name) for cell_name in cell_names)
        max_cell = max(
            constids.get_index(cell_name) for cell_name in cell_names)

        print(
            "static constexpr int32_t kFirstCellName = {};".format(min_cell),
            file=f)
        print(
            "static constexpr int32_t kCellCount = {};".format(max_cell -
                                                               min_cell + 1),
            file=f)

        all_max_bel_index = 0
        bel_counts = {}
        cells_in_prototypes = {}

        for idx, prototype_name in enumerate(self.prototype_names):
            prototype = self.prototypes[prototype_name]

            max_bel_index = 0
            max_cell_index = 0

            cells_in_prototype = set()
            for cell_type, bel_index in prototype.bel_cell_constraints:
                max_bel_index = max(bel_index + 1, max_bel_index)

                cell_index = constids.get_index(cell_type) - min_cell
                max_cell_index = max(cell_index, max_cell_index + 1)

                cells_in_prototype.add(cell_type)

            cells_in_prototypes[prototype_name] = cells_in_prototype
            bel_counts[prototype_name] = max_bel_index

            all_max_bel_index = max(all_max_bel_index, max_bel_index)

        print(
            "static constexpr size_t kBelCounts[PROTOTYPE_COUNT] = {", file=f)
        for idx, prototype_name in enumerate(self.prototype_names):
            if idx + 1 < len(self.prototype_names):
                comma = ','
            else:
                comma = ''

            print(
                "    /* [{}] = */ {}{}".format(
                    prototype_name, bel_counts[prototype_name], comma),
                file=f)
        print("};", file=f)
        print("", file=f)

        cell_flat_map = {}
        max_flat_cell_index = 0
        print(
            "static constexpr std::array<int32_t, kCellCount> kFlatCellIndex[PROTOTYPE_COUNT] = {",
            file=f)
        for idx, prototype_name in enumerate(self.prototype_names):
            cell_flat_map[prototype_name] = {}

            print("    /* [{}] = */ {{".format(prototype_name), file=f)

            flat_cell_index = 0
            cells_in_prototype = cells_in_prototypes[prototype_name]
            for cell_idx, cell_name in enumerate(cell_names):
                if cell_idx + 1 < len(cell_names):
                    comma = ','
                else:
                    comma = ''

                if cell_name in cells_in_prototype:
                    print(
                        "        /* [{}] = */ {}{}".format(
                            cell_name, flat_cell_index, comma),
                        file=f)
                    cell_flat_map[prototype_name][cell_name] = flat_cell_index
                    flat_cell_index += 1
                    max_flat_cell_index = max(max_flat_cell_index,
                                              flat_cell_index)
                else:
                    print(
                        "        /* [{}] = */ -1{}".format(cell_name, comma),
                        file=f)

            if idx + 1 < len(self.prototype_names):
                comma = ','
            else:
                comma = ''
            print("    }}{}".format(comma), file=f)

        print("};", file=f)
        print("", file=f)
        print(
            "static constexpr size_t kMaxBelIndex = {};".format(
                all_max_bel_index),
            file=f)
        print(
            "static constexpr size_t kMaxFlatCellIndex = {};".format(
                max_flat_cell_index),
            file=f)
        print("", file=f)

        for prototype_name in self.prototype_names:
            prototype = self.prototypes[prototype_name]

            print("enum Constraint_{}_Tags {{".format(prototype_name), file=f)
            for idx, tag_prefix in enumerate(sorted(prototype.tags)):
                print(
                    "    TAG_{}_{} = {},".format(prototype_name,
                                                 tag_prefix.replace('.', '_'),
                                                 idx),
                    file=f)

            print(
                "    TAG_{}_COUNT = {}".format(prototype_name,
                                               len(prototype.tags)),
                file=f)
            print("};", file=f)
            print("", file=f)

        print("", file=f)
        print(
            "typedef bool (*ConstraintFunction)(TagState *tags, BelId bel, bool explain);",
            file=f)
        print("", file=f)
        print(
            """static bool UndefinedConstraint(TagState *tags, BelId bel, bool explain) {
    NPNR_ASSERT(false);
    return false;
}""",
            file=f)
        print("", file=f)
        """
        for prototype_name in self.prototype_names:
            prototype = self.prototypes[prototype_name]
            for cell_type, bel_index in prototype.bel_cell_constraints:
                print("bool {}_bel{}_{}_isValidBelForCellType(TagState *tags, BelId bel, bool explain) {{".format(
                    prototype,
                    ), file=f)

                print("   return false;", file=f)
                print("}", file=f)

        print("static ConstraintFunction*** is_valid_bel_for_cell_type[PROTOTYPE_COUNT] = {", file=f)
        for idx, prototype_name in enumerate(self.prototype_names):
            prototype = self.prototypes[prototype_name]

            print('    /*[{}] = */ {{'.format(idx), file=f)

            for bel_index in range(all_max_bel_index+1):
                function_names = []
                for cell_index in range(min_cell, max_cell+1):
                    cell_type = constids.get(cell_index)

                    key = cell_type, bel_index

                    if key in prototype.bel_cell_constraints:
                        function_names.append("UndefinedConstraint")
                    else:
                        function_names.append("UndefinedConstraint")
                function_list = ','.join(function_names)

                if bel_index == all_max_bel_index:
                    comma = ''
                else:
                    comma = ','

                print('        /*[{}] = */ {{ {} }}{}'.format(bel_index, function_list, comma), file=f)

            if idx+1 == len(self.prototype_names):
                comma = ''
            else:
                comma = ','

            print('    }}{}'.format(comma), file=f)

        print("};", file=f)
        """

        f.write(CONSTRAINT_IMPLEMENTATION)

        f.write(BOTTOM_OF_FILE)
