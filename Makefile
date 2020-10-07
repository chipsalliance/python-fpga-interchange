# Copyright (C) 2020  The Symbiflow Authors.
#
# Use of this source code is governed by a ISC-style
# license that can be found in the LICENSE file or at
# https://opensource.org/licenses/ISC
#
# SPDX-License-Identifier: ISC
SHELL=bash

ALL_EXCLUDE = third_party .git env build
FORMAT_EXCLUDE = $(foreach x,$(ALL_EXCLUDE),-and -not -path './$(x)/*')

PYTHON_SRCS=$(shell find . -name "*py" $(FORMAT_EXCLUDE))

IN_ENV = if [ -e env/bin/activate ]; then . env/bin/activate; fi;
env:
	python3 -mvenv env
	$(IN_ENV) pip install --upgrade -r requirements.txt

format: ${PYTHON_SRCS}
	$(IN_ENV) yapf -i ${PYTHON_SRCS}

test-py:
	$(IN_ENV) pytest --doctest-modules

clean:
	rm -rf env

.PHONY: clean env build test-py
