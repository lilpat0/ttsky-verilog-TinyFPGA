# TinyFPGA — A Configurable FPGA-Style Logic Fabric

## Overview

TinyFPGA is a compact, reconfigurable FPGA-style logic fabric implemented as a TinyTapeout-compatible ASIC design. Rather than implementing one fixed digital function, it allows a user to configure lookup tables (LUTs), select the signals connected to their inputs, and choose whether each external output is combinational or registered.

The design contains four 4-input LUTs, a 16-source routing network, four LUT output registers, an 8-bit shared counter/PWM timebase, an 8-bit shift register, and one PWM output channel. Configuration is sent serially through a write-only SPI interface.

TinyFPGA is an educational demonstration of programmable logic and a small FPGA-like architecture. It is not intended to provide the resources or generality of a commercial FPGA.

## Features

- Four independent 4-input lookup tables (LUT4s).
- A 16-bit truth table for each LUT.
- Sixteen independently configurable LUT input connections (four per LUT).
- Routing sources include eight external inputs, four registered LUT outputs, the counter MSB, the counter terminal-count pulse, the shift-register MSB, and the PWM output.
- Four LUT output registers, with one configuration bit per output selecting registered or combinational output behavior.
- An 8-bit counter with a programmable terminal count and a one-clock terminal-count pulse.
- An 8-bit shift register with configurable initial value, input source, enable, and direction.
- One PWM channel using the shared counter/PWM timebase.
- SPI Mode 0 configuration, transmitted most-significant-bit first.
- Exact 164-bit frame-length validation.
- Fabric outputs are disabled while a configuration transaction is active and remain disabled after an invalid-length frame.
- Constant logic values can be generated using LUT truth tables (`16'h0000` or `16'hFFFF`).

## Architecture and How It Works

### 1. Lookup Tables

The core contains four LUT4 blocks. Each LUT receives four independently routed input signals. Those four bits form a 4-bit address into the LUT's 16-bit truth table:

```systemverilog
assign lut_result[i] = truth_table[lut_inputs];
