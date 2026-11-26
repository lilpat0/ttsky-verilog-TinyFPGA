
# SPDX-License-Identifier: Apache-2.0
# Cocotb tests for tt_um_tinyfpga
#
# TinyTapeout pin mapping:
#   ui_in[7:0]  = FPGA fabric inputs
#   uo_out[3:0] = FPGA fabric outputs
#
#   uio[0] = SPI SCLK
#   uio[1] = SPI CS_n
#   uio[2] = SPI MOSI
#   uio[3] = SPI MISO
#
# Configuration format (132 bits, MSB first):
#   [63:0]     Four 16-bit LUT truth tables
#   [127:64]   Sixteen 4-bit routing selectors
#   [131:128]  Four output register-mode bits

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer


CFG_BITS = 132
SPI_HALF = 4

SCLK = 0
CS_N = 1
MOSI = 2

R_IN = list(range(8))
R_Q = [8, 9, 10, 11]
R_0 = 12
R_1 = 13


# ============================================================
# LUT CONFIGURATION HELPERS
# ============================================================

def lut_from_func(func):
    """Generate a 16-bit LUT4 truth table."""

    table = 0

    for idx in range(16):
        a = (idx >> 0) & 1
        b = (idx >> 1) & 1
        c = (idx >> 2) & 1
        d = (idx >> 3) & 1

        if func(a, b, c, d):
            table |= 1 << idx

    return table


def build_cfg(luts, routes, reg_mode=0):
    """Build the complete 132-bit FPGA configuration."""

    assert len(luts) == 4
    assert len(routes) == 4
    assert all(len(r) == 4 for r in routes)

    cfg = 0

    for i in range(4):

        cfg |= (luts[i] & 0xFFFF) << (i * 16)

        for j in range(4):
            cfg |= (
                (routes[i][j] & 0xF)
                << (64 + (i * 4 + j) * 4)
            )

    cfg |= (reg_mode & 0xF) << 128

    return cfg


# ============================================================
# PIN HELPERS
# ============================================================

def set_spi(dut, sclk, cs_n, mosi):
    """Drive the three SPI input pins."""

    dut.uio_in.value = (
        (mosi << MOSI)
        | (cs_n << CS_N)
        | (sclk << SCLK)
    )


def outs(dut):
    """Read the four FPGA fabric outputs."""

    return int(dut.uo_out.value) & 0x0F


# ============================================================
# SPI CONFIGURATION HELPER
# ============================================================

async def spi_write(dut, value, nbits=CFG_BITS):
    """
    Send an SPI configuration transaction.

    Mode 0:
      SCLK idle low
      MOSI set up before rising edge
      MSB transmitted first

    CS is released after the final clock.
    """

    assert nbits > 0

    # Assert chip select.
    set_spi(dut, 0, 0, 0)
    await ClockCycles(dut.clk, SPI_HALF)

    # Transmit MSB first.
    for k in range(nbits - 1, -1, -1):

        bit = (value >> k) & 1

        # Set MOSI while clock is low.
        set_spi(dut, 0, 0, bit)
        await ClockCycles(dut.clk, SPI_HALF)

        # Rising SCLK edge.
        set_spi(dut, 1, 0, bit)
        await ClockCycles(dut.clk, SPI_HALF)

    # Return SCLK low.
    set_spi(dut, 0, 0, 0)
    await ClockCycles(dut.clk, SPI_HALF)

    # Release chip select.
    set_spi(dut, 0, 1, 0)

    # Allow synchronizers and configuration commit to settle.
    await ClockCycles(dut.clk, 10)


# ============================================================
# TEST INITIALIZATION
# ============================================================

async def start(dut):
    """Initialize the TinyFPGA test environment."""

    cocotb.start_soon(
        Clock(dut.clk, 100, unit="ns").start()
    )

    dut.ena.value = 1
    dut.ui_in.value = 0

    set_spi(dut, 0, 1, 0)

    dut.rst_n.value = 0

    await ClockCycles(dut.clk, 10)

    dut.rst_n.value = 1

    await ClockCycles(dut.clk, 5)


async def after_edge(dut):
    """Wait until after the next rising clock edge."""

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


# ============================================================
# TEST 1: RESET STATE
# ============================================================

@cocotb.test()
async def test_reset_state(dut):

    """Verify reset outputs and pin directions."""

    await start(dut)

    assert outs(dut) == 0

    assert int(dut.uio_oe.value) == 0b00001000

    assert int(dut.uio_out.value) == 0


# ============================================================
# TEST 2: COMBINATIONAL LOGIC
# ============================================================

@cocotb.test()
async def test_combinational_gates(dut):

    """Test AND, XOR, OR, and NOT across all 256 input patterns."""

    await start(dut)

    luts = [
        lut_from_func(lambda a, b, c, d: a & b),
        lut_from_func(lambda a, b, c, d: a ^ b),
        lut_from_func(lambda a, b, c, d: a | b),
        lut_from_func(lambda a, b, c, d: 1 - a),
    ]

    routes = [
        [R_IN[0], R_IN[1], R_0, R_0],
        [R_IN[2], R_IN[3], R_0, R_0],
        [R_IN[4], R_IN[5], R_0, R_0],
        [R_IN[6], R_0, R_0, R_0],
    ]

    await spi_write(dut, build_cfg(luts, routes))

    for v in range(256):

        dut.ui_in.value = v

        await ClockCycles(dut.clk, 2)

        i = [(v >> n) & 1 for n in range(8)]

        expected = (
            (i[0] & i[1])
            | ((i[2] ^ i[3]) << 1)
            | ((i[4] | i[5]) << 2)
            | ((1 - i[6]) << 3)
        )

        actual = outs(dut)

        assert actual == expected, (
            f"ui_in={v:#04x}: "
            f"got={actual:#x}, expected={expected:#x}"
        )


# ============================================================
# TEST 3: CONSTANT ROUTING
# ============================================================

@cocotb.test()
async def test_constants(dut):

    """Verify constant-zero and constant-one routing."""

    await start(dut)

    luts = [
        0xFFFF,
        0x0001,
        0x0001,
        0x0001,
    ]

    routes = [
        [R_1, R_1, R_1, R_1],
        [R_0, R_0, R_0, R_0],
        [14, 15, 14, 15],
        [R_0, R_0, R_0, R_1],
    ]

    await spi_write(dut, build_cfg(luts, routes))

    await ClockCycles(dut.clk, 2)

    assert outs(dut) == 0b0111


# ============================================================
# TEST 4: REGISTERED OUTPUT
# ============================================================

@cocotb.test()
async def test_registered_output(dut):

    """Verify registered outputs update on clock edges."""

    await start(dut)

    luts = [
        lut_from_func(lambda a, b, c, d: a & b),
        0,
        0,
        0,
    ]

    routes = [
        [R_IN[0], R_IN[1], R_0, R_0],
        [R_0] * 4,
        [R_0] * 4,
        [R_0] * 4,
    ]

    await spi_write(
        dut,
        build_cfg(luts, routes, reg_mode=0b0001)
    )

    await after_edge(dut)

    dut.ui_in.value = 0b11

    await Timer(10, unit="ns")

    assert outs(dut) & 1 == 0, (
        "Registered output changed before clock edge"
    )

    await after_edge(dut)

    assert outs(dut) & 1 == 1, (
        "Registered output failed to update"
    )

    await after_edge(dut)

    dut.ui_in.value = 0b01

    await Timer(10, unit="ns")

    assert outs(dut) & 1 == 1

    await after_edge(dut)

    assert outs(dut) & 1 == 0


# ============================================================
# TEST 5: REGISTERED FEEDBACK
# ============================================================

@cocotb.test()
async def test_toggle_feedback(dut):

    """Verify LUT0 can invert its own registered output."""

    await start(dut)

    luts = [
        lut_from_func(lambda a, b, c, d: 1 - a),
        0,
        0,
        0,
    ]

    routes = [
        [R_Q[0], R_0, R_0, R_0],
        [R_0] * 4,
        [R_0] * 4,
        [R_0] * 4,
    ]

    await spi_write(
        dut,
        build_cfg(luts, routes, reg_mode=0b0001)
    )

    samples = []

    for _ in range(10):

        await after_edge(dut)

        samples.append(outs(dut) & 1)

    assert set(samples) == {0, 1}, (
        f"Output never toggled: {samples}"
    )

    for a, b in zip(samples, samples[1:]):

        assert a != b, (
            f"Output did not toggle every clock: {samples}"
        )


# ============================================================
# TEST 6: LUT-TO-LUT PIPELINE
# ============================================================

@cocotb.test()
async def test_pipeline_crossbar(dut):

    """Verify LUT0 -> LUT1 registered feedback pipeline."""

    await start(dut)

    ident = lut_from_func(lambda a, b, c, d: a)

    luts = [
        ident,
        ident,
        0,
        0,
    ]

    routes = [
        [R_IN[0], R_0, R_0, R_0],
        [R_Q[0], R_0, R_0, R_0],
        [R_0] * 4,
        [R_0] * 4,
    ]

    await spi_write(
        dut,
        build_cfg(luts, routes, reg_mode=0b0011)
    )

    await after_edge(dut)

    dut.ui_in.value = 1

    await after_edge(dut)

    assert outs(dut) & 0b11 == 0b01

    await after_edge(dut)

    assert outs(dut) & 0b11 == 0b11


# ============================================================
# TEST 7: INVALID SPI TRANSFER LENGTHS
# ============================================================

@cocotb.test()
async def test_bad_length_rejected(dut):

    """
    Verify:
      131 bits = rejected
      132 bits = accepted
      133 bits = rejected
    """

    await start(dut)

    and_lut = lut_from_func(
        lambda a, b, c, d: a & b
    )

    good = build_cfg(
        [and_lut, 0, 0, 0],
        [
            [R_IN[0], R_IN[1], R_0, R_0],
            [R_0] * 4,
            [R_0] * 4,
            [R_0] * 4,
        ]
    )

    zero = build_cfg(
        [0, 0, 0, 0],
        [[R_0] * 4 for _ in range(4)]
    )

    # Load a valid configuration first.
    await spi_write(dut, good)

    dut.ui_in.value = 0b11

    await ClockCycles(dut.clk, 3)

    assert outs(dut) & 1 == 1

    # Invalid: 131 bits.
    await spi_write(
        dut,
        zero,
        nbits=CFG_BITS - 1
    )

    await ClockCycles(dut.clk, 3)

    assert outs(dut) & 1 == 1, (
        "131-bit transfer was incorrectly accepted"
    )

    # Invalid: 133 bits.
    await spi_write(
        dut,
        zero,
        nbits=CFG_BITS + 1
    )

    await ClockCycles(dut.clk, 3)

    assert outs(dut) & 1 == 1, (
        "133-bit transfer was incorrectly accepted"
    )

    # Valid: 132 bits.
    await spi_write(dut, zero)

    await ClockCycles(dut.clk, 3)

    assert outs(dut) & 1 == 0, (
        "Valid 132-bit transfer was rejected"
    )


# ============================================================
# TEST 8: RECONFIGURATION
# ============================================================

@cocotb.test()
async def test_reconfigure(dut):

    """Verify a second configuration replaces the first."""

    await start(dut)

    and_lut = lut_from_func(
        lambda a, b, c, d: a & b
    )

    or_lut = lut_from_func(
        lambda a, b, c, d: a | b
    )

    routes = [
        [R_IN[0], R_IN[1], R_0, R_0],
        [R_0] * 4,
        [R_0] * 4,
        [R_0] * 4,
    ]

    dut.ui_in.value = 0b01

    # First configuration: AND.
    await spi_write(
        dut,
        build_cfg(
            [and_lut, 0, 0, 0],
            routes
        )
    )

    await ClockCycles(dut.clk, 2)

    assert outs(dut) & 1 == 0

    # Second configuration: OR.
    await spi_write(
        dut,
        build_cfg(
            [or_lut, 0, 0, 0],
            routes
        )
    )

    await ClockCycles(dut.clk, 2)

    assert outs(dut) & 1 == 1
