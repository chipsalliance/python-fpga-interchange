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

import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="python-fpga-interchange",
    version="0.0.13",
    author="SymbiFlow Authors",
    author_email="symbiflow@lists.librecores.org",
    description="Python library for reading and writing FPGA interchange files",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/SymbiFlow/python-fpga-interchange",
    python_requires=">=3.7",
    packages=setuptools.find_packages(),
    include_package_data=True,
    install_requires=["pycapnp", "python-sat"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: ISC License",
        "Operating System :: OS Independent",
    ],
    entry_points={
        'console_scripts': [
            'fpga_inter_add_prim_lib=fpga_interchange.add_prim_lib:main',
            'fpga_inter_convert=fpga_interchange.convert:main',
            'fpga_inter_nextpnr_emit=fpga_interchange.nextpnr_emit:main',
            'fpga_inter_patch=fpga_interchange.patch:main',
            'fpga_inter_yosys_json=fpga_interchange.yosys_json:main',
            'fpga_inter_fasm_generator=fpga_interchange.fasm_generator:main',
        ],
    })
