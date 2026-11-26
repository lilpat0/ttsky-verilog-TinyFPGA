# SPDX-License-Identifier: Apache-2.0
# cocotb tests for tt_um_tinyfpga
#
# Pin map (see info.yaml):
#   ui_in[7:0]  fabric inputs         uo_out[3:0] fabric outputs
#   uio[0] SCLK   uio[1] CS_n   uio[2] MOSI   uio[3] MISO (output)
#
# Config layout (132 bits, MSB first on the wire):
#   [ 63:  0] 4 x 16-bit LUT tables, LUT i at [i*16 +: 16]
#   [127: 64] 16 x 4-bit route selects, LUT i input j at [64 + (i*4+j)*4 +: 4]
#   [131:128] reg_mode, bit i = 1 -> output i is registered
# Route select: 0-7 ui_in[n], 8-11 registered LUT outputs 0-3,
#               12 const 0, 13 const 1, 14/15 const 0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer

CFG_BITS = 132
SPI_HALF = 4  # clk cycles per SCLK half period (SCLK = clk/8, needs >= clk/4)

SCLK, CS_N, MOSI = 0, 1, 2

# Route select codes
R_IN = list(range(8))
R_Q = [8, 9, 10, 11]
R_0, R_1 = 12, 13


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def lut_from_func(f):
    """Build a 16-bit truth table. LUT input j is bit j of the table index."""
    table = 0
    for idx in range(16):
        a, b, c, d = (idx >> 0) & 1, (idx >> 1) & 1, (idx >> 2) & 1, (idx >> 3) & 1
        if f(a, b, c, d):
            table |= 1 << idx
    return table


def build_cfg(luts, routes, reg_mode=0):
    """luts: 4 ints, routes: 4 lists of 4 route codes, reg_mode: 4-bit int."""
    cfg = 0
    for i in range(4):
        cfg |= (luts[i] & 0xFFFF) << (i * 16)
        for j in range(4):
            cfg |= (routes[i][j] & 0xF) << (64 + (i * 4 + j) * 4)
    cfg |= (reg_mode & 0xF) << 128
    return cfg


def set_spi(dut, sclk, cs_n, mosi):
    dut.uio_in.value = (mosi << MOSI) | (cs_n << CS_N) | (sclk << SCLK)


async def spi_write(dut, value, nbits=CFG_BITS):
    """Send the low `nbits` of `value`, MSB first, SPI mode 0."""
    set_spi(dut, 0, 0, 0)  # assert CS
    await ClockCycles(dut.clk, SPI_HALF)
    for k in range(nbits - 1, -1, -1):
        bit = (value >> k) & 1
        set_spi(dut, 0, 0, bit)  # data set up while SCLK low
        await ClockCycles(dut.clk, SPI_HALF)
        set_spi(dut, 1, 0, bit)  # rising edge: slave samples
        await ClockCycles(dut.clk, SPI_HALF)
    set_spi(dut, 0, 0, 0)
    await ClockCycles(dut.clk, SPI_HALF)
    set_spi(dut, 0, 1, 0)  # deassert CS -> commit
    await ClockCycles(dut.clk, 8)  # let synchronizers + commit settle


async def start(dut):
    cocotb.start_soon(Clock(dut.clk, 100, "ns").start())  # 10 MHz
    dut.ena.value = 1
    dut.ui_in.value = 0
    set_spi(dut, 0, 1, 0)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)


async def after_edge(dut, ns=1):
    """Wait for the next clk rising edge and a hair beyond it."""
    await RisingEdge(dut.clk)
    await Timer(ns, "ns")


def outs(dut):
    return int(dut.uo_out.value)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_reset_state(dut):
    """After reset: outputs low, only MISO is driven, MISO low."""
    await start(dut)
    assert outs(dut) == 0
    assert int(dut.uio_oe.value) == 0b0000_1000
    assert int(dut.uio_out.value) == 0


@cocotb.test()
async def test_combinational_gates(dut):
    """AND / XOR / OR / NOT in the four LUTs, all 256 input patterns."""
    await start(dut)

    luts = [
        lut_from_func(lambda a, b, c, d: a & b),  # out0 = in0 & in1
        lut_from_func(lambda a, b, c, d: a ^ b),  # out1 = in2 ^ in3
        lut_from_func(lambda a, b, c, d: a | b),  # out2 = in4 | in5
        lut_from_func(lambda a, b, c, d: 1 - a),  # out3 = ~in6
    ]
    routes = [
        [R_IN[0], R_IN[1], R_0, R_0],
        [R_IN[2], R_IN[3], R_0, R_0],
        [R_IN[4], R_IN[5], R_0, R_0],
        [R_IN[6], R_0, R_0, R_0],
    ]
    await spi_write(dut, build_cfg(luts, routes, reg_mode=0))

    for v in range(256):
        dut.ui_in.value = v
        await ClockCycles(dut.clk, 2)
        i = [(v >> n) & 1 for n in range(8)]
        exp = (
            (i[0] & i[1])
            | ((i[2] ^ i[3]) << 1)
            | ((i[4] | i[5]) << 2)
            | ((1 - i[6]) << 3)
        )
        assert outs(dut) == exp, f"ui_in={v:#04x}: got {outs(dut):#x}, want {exp:#x}"


@cocotb.test()
async def test_constants(dut):
    """Route codes 12/14/15 read as 0 and 13 reads as 1."""
    await start(dut)

    luts = [
        0x8000,  # index 15 -> 1
        0x0001,  # index 0  -> 1
        0x0001,  # index 0  -> 1 (14/15 behave as 0)
        0x0001,  # index 8 (input d = const 1) -> table[8] = 0
    ]
    routes = [
        [R_1, R_1, R_1, R_1],
        [R_0, R_0, R_0, R_0],
        [14, 15, 14, 15],
        [R_0, R_0, R_0, R_1],
    ]
    await spi_write(dut, build_cfg(luts, routes, reg_mode=0))
    await ClockCycles(dut.clk, 2)
    assert outs(dut) == 0b0111


@cocotb.test()
async def test_registered_output(dut):
    """reg_mode=1: output updates one clk after the input changes."""
    await start(dut)

    luts = [lut_from_func(lambda a, b, c, d: a & b), 0, 0, 0]
    routes = [[R_IN[0], R_IN[1], R_0, R_0]] + [[R_0] * 4] * 3
    await spi_write(dut, build_cfg(luts, routes, reg_mode=0b0001))

    await after_edge(dut)
    dut.ui_in.value = 0b11
    await Timer(10, "ns")
    assert outs(dut) & 1 == 0, "registered output changed before the clock edge"
    await after_edge(dut)
    assert outs(dut) & 1 == 1, "registered output did not update on the clock edge"

    await after_edge(dut)
    dut.ui_in.value = 0b01
    await Timer(10, "ns")
    assert outs(dut) & 1 == 1
    await after_edge(dut)
    assert outs(dut) & 1 == 0


@cocotb.test()
async def test_toggle_feedback(dut):
    """LUT0 inverts its own register (route 8): output toggles every clk."""
    await start(dut)

    luts = [lut_from_func(lambda a, b, c, d: 1 - a), 0, 0, 0]
    routes = [[R_Q[0], R_0, R_0, R_0]] + [[R_0] * 4] * 3
    await spi_write(dut, build_cfg(luts, routes, reg_mode=0b0001))

    samples = []
    for _ in range(10):
        await after_edge(dut)
        samples.append(outs(dut) & 1)
    assert set(samples) == {0, 1}, f"output never toggled: {samples}"
    for a, b in zip(samples, samples[1:]):
        assert a != b, f"output did not toggle every clock: {samples}"


@cocotb.test()
async def test_pipeline_crossbar(dut):
    """LUT0 registers in0, LUT1 registers LUT0's register: 2-clk pipeline."""
    await start(dut)

    ident = lut_from_func(lambda a, b, c, d: a)
    luts = [ident, ident, 0, 0]
    routes = [
        [R_IN[0], R_0, R_0, R_0],
        [R_Q[0], R_0, R_0, R_0],
        [R_0] * 4,
        [R_0] * 4,
    ]
    await spi_write(dut, build_cfg(luts, routes, reg_mode=0b0011))

    await after_edge(dut)
    dut.ui_in.value = 1
    await after_edge(dut)
    assert outs(dut) & 0b11 == 0b01
    await after_edge(dut)
    assert outs(dut) & 0b11 == 0b11


@cocotb.test()
async def test_bad_length_rejected(dut):
    """Transfers of 131 or 133 bits must not change the config."""
    await start(dut)

    luts = [lut_from_func(lambda a, b, c, d: a & b), 0, 0, 0]
    routes = [[R_IN[0], R_IN[1], R_0, R_0]] + [[R_0] * 4] * 3
    good = build_cfg(luts, routes, reg_mode=0)
    zero = build_cfg([0, 0, 0, 0], [[R_0] * 4] * 4, reg_mode=0)

    await spi_write(dut, good)
    dut.ui_in.value = 0b11
    await ClockCycles(dut.clk, 3)
    assert outs(dut) & 1 == 1

    await spi_write(dut, zero, nbits=CFG_BITS - 1)
    await ClockCycles(dut.clk, 3)
    assert outs(dut) & 1 == 1, "131-bit transfer was accepted"

    await spi_write(dut, zero, nbits=CFG_BITS + 1)
    await ClockCycles(dut.clk, 3)
    assert outs(dut) & 1 == 1, "133-bit transfer was accepted"

    await spi_write(dut, zero)  # correct length: now it must load
    await ClockCycles(dut.clk, 3)
    assert outs(dut) & 1 == 0, "valid 132-bit transfer was rejected"


@cocotb.test()
async def test_reconfigure(dut):
    """A second valid transfer fully replaces the first config."""
    await start(dut)

    and_lut = lut_from_func(lambda a, b, c, d: a & b)
    or_lut = lut_from_func(lambda a, b, c, d: a | b)
    routes = [[R_IN[0], R_IN[1], R_0, R_0]] + [[R_0] * 4] * 3

    dut.ui_in.value = 0b01
    await spi_write(dut, build_cfg([and_lut, 0, 0, 0], routes))
    await ClockCycles(dut.clk, 2)
    assert outs(dut) & 1 == 0

    await spi_write(dut, build_cfg([or_lut, 0, 0, 0], routes))
    await ClockCycles(dut.clk, 2)
    assert outs(dut) & 1 == 1
