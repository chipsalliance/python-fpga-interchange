# -*- coding: utf-8 -*-
#
# Copyright (C) 2020  The SymbiFlow Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC


class AssertStateVariable():
    """ Abstract asserted state variable. """

    def __init__(self, parent, state):
        self.parent = parent
        self.state = state

    def variable_name(self):
        return '{}.{}'.format(self.parent.prefix, self.state)

    def variable(self, solver):
        return solver.get_variable(self.variable_name())

    def __str__(self):
        return self.variable_name()


class DeassertStateVariable():
    """ Abstract deasserted state variable. """

    def __init__(self, parent, state):
        self.parent = parent
        self.state = state

    def variable_name(self):
        return '{}.NOT.{}'.format(self.parent.prefix, self.state)

    def variable(self, solver):
        return solver.get_variable(self.variable_name())

    def __str__(self):
        return self.variable_name()


class Not():
    """ Abstract inverted variable. """

    def __init__(self, variable):
        self.a_variable = variable

    def variable_name(self):
        return self.a_variable.variable_name()

    def variable(self, solver):
        return -solver.get_variable(self.variable_name())

    def __str__(self):
        return '!' + self.variable_name()


class Xor():
    """ Abstract XOR SAT clause. """

    def __init__(self, variable_a, variable_b):
        self.variable_a = variable_a
        self.variable_b = variable_b

    def clauses(self):
        yield [self.variable_a, self.variable_b]
        yield [Not(self.variable_a), Not(self.variable_b)]

    def __str__(self):
        return '{} xor {}'.format(self.variable_a.variable_name(),
                                  self.variable_b.variable_name())


class Implies():
    """ Abstract implies (->) SAT clause. """

    def __init__(self, source_variable, target_variable):
        self.source_variable = source_variable
        self.target_variable = target_variable

    def clauses(self):
        yield [Not(self.source_variable), self.target_variable]

    def __str__(self):
        return '{} -> {}'.format(self.source_variable.variable_name(),
                                 self.target_variable.variable_name())


class Or():
    """ Abstract OR SAT clause. """

    def __init__(self, variables):
        self.variables = variables

    def clauses(self):
        yield self.variables

    def __str__(self):
        return 'sum({})'.format(', '.join(str(var) for var in self.variables))


class ExclusiveStateGroup():
    """ A group of states that have at most 1 state selected. """

    def __init__(self, prefix, default):
        self.prefix = prefix
        self.states = set()
        self.default = default

    def name(self):
        """ Return name of state group. """
        return self.prefix

    def add_state(self, state):
        """ Add a state to this group. """
        self.states.add(state)

    def assert_state(self, state):
        """ Return a SAT variable that asserts that a state must be asserted. """
        return AssertStateVariable(self, state)

    def deassert_state(self, state):
        """ Return a SAT variable that asserts that a state must be deasserted. """
        return DeassertStateVariable(self, state)

    def select_one(self):
        """ Yields SAT clauses that ensure that one variable from this state group is selected. """
        yield Or([self.assert_state(state) for state in self.states])

    def implies_clause(self, source_variable, state):
        """ Yields SAT clauses that ensure if source_variable is true, then state is asserted from this group. """
        assert state in self.states, state
        yield Implies(source_variable, self.assert_state(state))

    def implies_not_clause(self, source_variable, state):
        """ Yields SAT clauses that ensure if source_variable is true, then state is deassert from this group. """
        assert state in self.states
        yield Implies(source_variable, self.deassert_state(state))

    def requires_clause(self, source_variable, states):
        """ Yields SAT clauses that ensure if source_variable is true, then one of the supplied states must be asserted from this group. """
        for other_state in self.states - states:
            yield self.implies_not_clause(source_variable, other_state)

    def variables(self):
        """ Yields SAT variables generated from this state group. """
        for state in self.states:
            yield self.assert_state(state)
            yield self.deassert_state(state)

    def clauses(self):
        """ Yield SAT clauses that ensure this state group selects at most one state. """
        for state in self.states:
            yield Xor(
                AssertStateVariable(self, state),
                DeassertStateVariable(self, state))
            for other_state in (self.states - set([state])):
                yield Implies(
                    AssertStateVariable(self, state),
                    DeassertStateVariable(self, other_state))

    def get_state(self, variables_for_state_group):
        """ Return state for this group based on true SAT variables relevant to this group. """
        state = None
        for variable in variables_for_state_group:
            assert variable.startswith(self.prefix + '.')
            data_portion = variable[len(self.prefix) + 1:]

            not_set = False
            if data_portion.startswith('NOT.'):
                data_portion = data_portion[len('NOT.'):]
                not_set = True

            assert data_portion in self.states

            if not_set:
                continue

            if state is None:
                state = data_portion
            else:
                assert False, (state, data_portion)

        if state is None:
            state = self.default

        return state


class Solver():
    """ Abstract SAT solver, where each SAT variable is a string.

    Clauses used in this class are "abstract" clauses, that can yield more than
    one clause.

    """

    def __init__(self):
        self.variable_names = set()
        self.variable_name_to_index = None
        self.abstract_clauses = []
        self.state_group_names = set()
        self.state_groups = []
        self.variable_to_state_group = {}

    def add_state_group(self, state_group):
        """ Adds a state group to the solver.

        state_group (ExclusiveStateGroup) - State group.

        """
        assert state_group.name() not in self.state_group_names
        self.state_group_names.add(state_group.name())
        self.state_groups.append(state_group)

    def add_variable_names(self, variables):
        """ Adds a variable names to this Solver.

        These variable names cannot already be apart of the Solver.

        """
        new_variable_names = set()
        for variable in variables:
            new_variable_names.add(variable)

        assert len(self.variable_names & variables) == 0

        self.variable_names |= new_variable_names

    def add_clause(self, clause):
        """ Add an abstract clause to the Solver.

        Interface for abstract clause should have one method that yields a
        list of abstract variable objects.

        Abstract variable objects should have a method called variable, that
        takes a Solver object.

        """
        self.abstract_clauses.append(clause)

    def get_variable(self, variable_name):
        """ Return SAT variable index for a variable name. """
        assert self.variable_name_to_index is not None
        return self.variable_name_to_index[variable_name]

    def get_variable_name(self, variable_index):
        """ Return a SAT variable name for a given variable index. """
        return self.variable_names[variable_index - 1]

    def prepare_for_sat(self):
        """ Convert SAT clauses using variable name strings to SAT indicies """

        for state_group in self.state_groups:
            new_variables = set()
            for variable in state_group.variables():
                new_variables.add(variable.variable_name())

            self.add_variable_names(new_variables)

            for variable in new_variables:
                assert variable not in self.variable_to_state_group
                self.variable_to_state_group[variable] = state_group

            for clause in state_group.clauses():
                self.add_clause(clause)

        self.variable_names = sorted(self.variable_names)
        self.variable_name_to_index = {}

        # Assign SAT variables indicies to variable names
        for idx, variable_name in enumerate(self.variable_names):
            assert variable_name not in self.variable_name_to_index
            self.variable_name_to_index[variable_name] = idx + 1

        # Convert abstract clauses using variable names to SAT clauses
        concrete_clauses = set()
        for abstract_clause in self.abstract_clauses:
            for clause in abstract_clause.clauses():
                concrete_clause = []
                for part in clause:
                    concrete_clause.append(part.variable(self))

                assert len(set(concrete_clause)) == len(concrete_clause)
                concrete_clauses.add(tuple(sorted(concrete_clause)))

        return sorted(concrete_clauses)

    def decode_solution_model(self, sat_model):
        """ Decode a solution from a SAT solver.

        Returns a dict of state group states and a set of SAT variables that
        don't belong to state group states.

        """
        state_group_variables = {}
        other_variables = set()

        for idx in sat_model:
            if idx < 0:
                continue

            variable = self.get_variable_name(idx)

            if variable in self.variable_to_state_group:
                state_group = self.variable_to_state_group[variable]

                state_group_name = state_group.name()
                if state_group_name not in state_group_variables:
                    state_group_variables[state_group_name] = set()

                state_group_variables[state_group_name].add(variable)
            else:
                other_variables.add(variable)

        state_group_results = {}
        for state_group_name, variables in state_group_variables.items():
            state_group = self.variable_to_state_group[list(variables)[0]]
            state_group_results[state_group_name] = state_group.get_state(
                variables)

        return state_group_results, other_variables

    def print_debug(self):
        """ Print debugging information for the abstract SAT solver. """
        print()
        print("Variable names ({} total):".format(len(self.variable_names)))
        print()
        for variable in self.variable_names:
            print(variable)
        print()

        print("Clauses:")
        print()
        for clause in self.abstract_clauses:
            print(clause)
