# TinyFPGA — A Configurable FPGA Fabric

## Overview

TinyFPGA is a compact, reconfigurable FPGA-style logic fabric designed to demonstrate the fundamental concepts behind field-programmable gate arrays (FPGAs) in a TinyTapeout-compatible ASIC.

Instead of implementing a fixed digital circuit, TinyFPGA allows users to configure lookup tables (LUTs), routing connections, and registered outputs through an SPI interface. This makes it possible to implement different digital logic functions without modifying the hardware itself.

The project is designed around a small four-LUT architecture, providing a hands-on introduction to programmable logic, digital design, hardware configuration, and FPGA architecture.

## Features

- Four independent 4-input lookup tables (LUT4s).
- 16-bit truth table for each LUT.
- Configurable routing network connecting external inputs and LUT outputs.
- Four independently configurable registered outputs.
- SPI configuration interface.
- Support for combinational and sequential logic.
- Constant logic-zero and logic-one routing sources.
- Compact architecture designed for TinyTapeout.

## How It Works

### 1. Lookup Tables

The core of TinyFPGA consists of four LUT4 blocks.

Each LUT has four inputs and a 16-bit configuration table. The four input signals form a 4-bit address that selects one of the 16 truth-table bits.

This allows each LUT to implement any Boolean function of up to four inputs.

For example:

| Function | Truth table |
|---|---|
| AND | `16'h8000` |
| OR | `16'hFFFE` |
| XOR | `16'h6996` |
| NOT A | Depends on input ordering |

Each LUT can be configured independently, allowing multiple logic functions to operate simultaneously.

### 2. Programmable Routing

The routing network connects the LUT inputs to different signal sources.

Each of the four LUTs has four independently configurable input connections, giving the fabric 16 routing selectors.

Each routing selector is four bits wide and supports the following sources:

| Selector | Source |
|---|---|
| 0–7 | External inputs `io_in[7:0]` |
| 8–11 | Registered LUT outputs |
| 12 | Logic 0 |
| 13 | Logic 1 |
| 14–15 | Logic 0 |

This allows LUTs to receive external signals, outputs from other LUTs, or constant values.

The routing network also supports feedback, allowing sequential logic and more complex interconnected circuits to be constructed.

### 3. Registered Outputs

Each LUT has an associated output register.

A configuration bit controls whether the corresponding fabric output uses the registered LUT output or the combinational LUT result.

This provides two operating modes:

- **Combinational mode:** The output changes as its LUT inputs change.
- **Registered mode:** The output updates on the rising edge of the system clock.

Registered outputs can also be used as routing sources for other LUTs, enabling sequential logic such as pipelines, counters, and state machines.

## Configuration Interface

TinyFPGA is configured through a serial peripheral interface (SPI).

The interface uses:

- SPI Mode 0 (CPOL = 0, CPHA = 0).
- Most-significant-bit first transmission.
- A 132-bit configuration frame.
- Write-only configuration; MISO is held low.

### SPI Signals

| Signal | Description |
|---|---|
| `spi_sclk` | SPI serial clock |
| `spi_cs_n` | Active-low chip select |
| `spi_mosi` | Configuration data input |
| `spi_miso` | Serial data output (held low) |

The configuration is transferred while chip select is low. A complete configuration frame contains exactly 132 bits.

### Configuration Bit Layout

| Bits | Width | Description |
|---|---:|---|
| `[63:0]` | 64 bits | Four LUT truth tables |
| `[127:64]` | 64 bits | Sixteen routing selectors |
| `[131:128]` | 4 bits | Output register-mode controls |

The LUT truth tables are arranged as four 16-bit values. Each routing selector occupies four bits.

The configuration frame is transmitted most-significant-bit first.

A complete 132-bit frame is required to update the configuration.

## How to Use TinyFPGA

### Step 1: Choose Your Logic Functions

Decide what each of the four LUTs should implement.

For example, you could configure:

- LUT 0 as an AND gate.
- LUT 1 as an XOR gate.
- LUT 2 as an OR gate.
- LUT 3 as an inverter.

Each LUT's truth table determines its Boolean function.

### Step 2: Configure the Routing

Select which signals connect to each LUT input.

You can connect LUT inputs to:
- The eight external inputs.
- The four registered LUT outputs.
- Constant logic 0.
- Constant logic 1.

This determines how the four LUTs interact with each other and with the outside world.

### Step 3: Select Output Modes

Configure the four register-mode bits.

Set a bit to select the registered output for that LUT, or clear it to use the combinational result.

### Step 4: Send the Configuration

Connect an SPI master to the TinyFPGA interface.

Transmit the complete 132-bit configuration frame using SPI Mode 0, most-significant-bit first.

The configuration is loaded when the chip select signal returns high after a valid transfer.

### Step 5: Apply Inputs

Drive the eight external input signals and observe the four fabric outputs.

The outputs reflect the programmed LUT functions, routing connections, and register settings.

## TinyTapeout Pin Connections

The TinyTapeout wrapper exposes the FPGA fabric through the standard project interface.

| TinyTapeout Signal | Function |
|---|---|
| `ui_in[7:0]` | Eight external FPGA inputs |
| `uo_out[3:0]` | Four FPGA outputs |
| `uio_in[0]` | SPI clock |
| `uio_in[1]` | SPI chip select |
| `uio_in[2]` | SPI MOSI |
| `uio_out[3]` | SPI MISO |
| `clk` | System clock |
| `rst_n` | Active-low reset |
| `ena` | TinyTapeout enable |

The remaining unused output pins are held low, and the bidirectional GPIO direction configuration enables only the MISO output.

## Example Applications

Although the fabric is small, it can demonstrate several important digital design concepts.

Possible applications include:

- Basic logic gates and Boolean functions.
- Combinational logic circuits.
- Multiplexers and decoders.
- Small arithmetic and control circuits.
- Sequential logic and pipelines.
- Finite-state machines.
- Programmable digital experiments.

The goal is to provide a small but functional programmable logic platform that users can experiment with and build upon.

## Project Sponsorship — BeaverWorks

This project was sponsored by **BeaverWorks**.

BeaverWorks supported the development of this project, helping make it possible to explore custom digital hardware design and the fundamentals of programmable logic through a real ASIC implementation.

The project reflects the value of hands-on engineering, experimentation, and learning through building. By implementing a configurable FPGA-style fabric in silicon, TinyFPGA provides an opportunity to explore concepts normally associated with larger programmable devices in a compact, accessible format.

**Special thanks to BeaverWorks for sponsoring and supporting this project.**

## Project Goals

TinyFPGA was developed to explore how the fundamental building blocks of an FPGA can be implemented in a small ASIC.

The project combines lookup tables, programmable routing, sequential logic, and serial configuration into a single compact design.

Rather than being a replacement for a commercial FPGA, TinyFPGA is an educational demonstration of the architecture and principles that make programmable hardware possible.
