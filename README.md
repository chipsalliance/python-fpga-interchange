FPGA Interchange
----------------

This python module is designed to read and write FPGA interchange files, and
provide some interoperability with other common formats.

Capabilities
------------

This library is planned to support the following capabilities:
 - Generate FPGA interchange files using Pythonic object model
 - (Planned) Read FPGA interchange files into Pythonic object model
 - Sanity check logical netlist for completeness and correctness.
 - (Planned) Sanity check a logical and physical netlist for completeness and
   correctness, given a device database.
 - (Planned) Read some common logical netlist formats in Pythonic object model:
   - eblif
   - Yosys Netlist JSON
