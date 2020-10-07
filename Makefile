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
	$(IN_ENV) cd tests; PYTHONPATH=../ python -m unittest

clean:
	rm -rf env

.PHONY: clean env build test-py
