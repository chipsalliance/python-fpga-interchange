#!/bin/bash

make format
test $(git status --porcelain | wc -l) -eq 0 || { git diff; false;  }
