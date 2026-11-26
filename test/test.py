
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

CFG_BITS = 132
SPI_HALF = 4

R_Q = [8, 9, 10, 11]
R_0 = 12
R_1 = 13


# ------------------------------------------------------------
# TinyTapeout pin helpers
# ------------------------------------------------------------

def set_spi_pins(dut, sclk=0, cs_n=1, mosi=0):
    value = (
        ((sclk & 1) << 0)
        | ((cs_n & 1) << 1)
        | ((mosi & 1) << 2)
    )
    dut.uio_in.value = value


def read_output(dut):
    return int(dut.uo_out.value) & 0x0F


def read_miso(dut):
    return (int(dut.uio_out.value) >> 3) & 1


async def cycles(dut, count=1):
    for _ in range(count):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")


# ------------------------------------------------------------
# Configuration builder
# ------------------------------------------------------------

def build_cfg(luts, routes, reg_mode=0):

    assert len(luts) == 4
    assert len(routes) == 4

    cfg = 0

    # Four 16-bit LUT truth tables: bits [63:0]
    for i in range(4):
        assert 0 <= luts[i] <= 0xFFFF
        cfg |= (luts[i] & 0xFFFF) << (i * 16)

    # Sixteen 4-bit routing selectors: bits [127:64]
    for i in range(4):
        assert len(routes[i]) == 4

        for j in range(4):
            route = routes[i][j]
            assert 0 <= route <= 15

            position = 64 + (i * 4 + j) * 4
            cfg |= (route & 0xF) << position

    # Four register-mode bits: bits [131:128]
    cfg |= (reg_mode & 0xF) << 128

    return cfg


# ------------------------------------------------------------
# SPI Mode 0, MSB first
# ------------------------------------------------------------

async def spi_write(dut, value, nbits=CFG_BITS):

    assert 0 < nbits <= 255

    set_spi_pins(dut, sclk=0, cs_n=0, mosi=0)
    await cycles(dut, 8)

    for bit in range(nbits - 1, -1, -1):

        mosi = (value >> bit) & 1

        # Data stable before rising edge
        set_spi_pins(dut, sclk=0, cs_n=0, mosi=mosi)
        await cycles(dut, SPI_HALF)

        # SPI Mode 0 sampling edge
        set_spi_pins(dut, sclk=1, cs_n=0, mosi=mosi)
        await cycles(dut, SPI_HALF)

        # Return clock low
        set_spi_pins(dut, sclk=0, cs_n=0, mosi=mosi)

    await cycles(dut, 8)

    # End transaction
    set_spi_pins(dut, sclk=0, cs_n=1, mosi=0)
    await cycles(dut, 10)


# ------------------------------------------------------------
# Reset and initialization
# ------------------------------------------------------------

async def start(dut):

    dut.clk.value = 0
    dut.rst_n.value = 0
    dut.ena.value = 1

    dut.ui_in.value = 0
    set_spi_pins(dut)

    cocotb.start_soon(
        Clock(dut.clk, 10, unit="ns").start()
    )

    await cycles(dut, 5)

    dut.rst_n.value = 1

    await cycles(dut, 10)


async def configure(dut, luts, routes, reg_mode=0):

    cfg = build_cfg(luts, routes, reg_mode)

    await spi_write(dut, cfg)

    await cycles(dut, 3)


# ------------------------------------------------------------
# TEST 1: Reset and TinyTapeout pin mapping
# ------------------------------------------------------------

@cocotb.test()
async def test_reset(dut):

    await start(dut)

    assert read_output(dut) == 0
    assert read_miso(dut) == 0

    assert int(dut.uio_oe.value) == 0x08

    dut._log.info("PASS: reset and TinyTapeout pin mapping")


# ------------------------------------------------------------
# TEST 2: LUT functionality
# ------------------------------------------------------------

@cocotb.test()
async def test_lut_logic(dut):

    await start(dut)

    # LUT0 = A AND B
    # LUT1 = A XOR B
    # LUT2 = A OR B
    # LUT3 = NOT A

    luts = [
        0x0008,
        0x6996,
        0x000E,
        0x5555
    ]

    routes = [
        [0, 1, R_0, R_0],
        [0, 1, R_0, R_0],
        [0, 1, R_0, R_0],
        [0, R_0, R_0, R_0]
    ]

    await configure(dut, luts, routes)

    for value in range(256):

        dut.ui_in.value = value

        await cycles(dut, 2)

        result = read_output(dut)

        a = value & 1
        b = (value >> 1) & 1

        expected = (
            (a & b)
            | ((a ^ b) << 1)
            | ((a | b) << 2)
            | ((1 - a) << 3)
        )

        assert result == expected, (
            f"Input={value:02X}, "
            f"Expected={expected:04b}, "
            f"Got={result:04b}"
        )

    dut._log.info("PASS: all 256 input combinations")


# ------------------------------------------------------------
# TEST 3: Constant routing
# ------------------------------------------------------------

@cocotb.test()
async def test_constants(dut):

    await start(dut)

    luts = [
        0x8000,
        0x0001,
        0x0001,
        0x0001
    ]

    routes = [
        [R_1, R_1, R_1, R_1],
        [R_0, R_0, R_0, R_0],
        [14, 15, 14, 15],
        [R_0, R_0, R_0, R_1]
    ]

    await configure(dut, luts, routes)

    dut.ui_in.value = 0

    await cycles(dut, 3)

    result = read_output(dut)

    expected = 0b0111

    assert result == expected, (
        f"Expected={expected:04b}, Got={result:04b}"
    )

    dut._log.info("PASS: constant routing")


# ------------------------------------------------------------
# TEST 4: Registered outputs
# ------------------------------------------------------------

@cocotb.test()
async def test_registered_outputs(dut):

    await start(dut)

    # Each LUT implements external input 0.
    luts = [0xAAAA] * 4

    routes = [
        [0, R_0, R_0, R_0]
        for _ in range(4)
    ]

    await configure(
        dut,
        luts,
        routes,
        reg_mode=0xF
    )

    dut.ui_in.value = 1

    await cycles(dut, 2)

    assert read_output(dut) == 0xF

    dut.ui_in.value = 0

    # Registered outputs hold their previous values
    # until the next rising clock edge.
    await Timer(1, unit="ns")

    assert read_output(dut) == 0xF

    await cycles(dut, 1)

    assert read_output(dut) == 0x0

    dut._log.info("PASS: registered output behavior")


# ------------------------------------------------------------
# TEST 5: LUT feedback
# ------------------------------------------------------------

@cocotb.test()
async def test_lut_feedback(dut):

    await start(dut)

    # LUT0 = NOT its own registered output.

    luts = [
        0x5555,
        0x0000,
        0x0000,
        0x0000
    ]

    routes = [
        [R_Q[0], R_0, R_0, R_0],
        [R_0, R_0, R_0, R_0],
        [R_0, R_0, R_0, R_0],
        [R_0, R_0, R_0, R_0]
    ]

    await configure(
        dut,
        luts,
        routes,
        reg_mode=0x1
    )

    previous = read_output(dut) & 1

    for _ in range(10):

        await cycles(dut, 1)

        result = read_output(dut) & 1

        assert result != previous, (
            "Feedback LUT did not toggle"
        )

        previous = result

    dut._log.info("PASS: LUT feedback")


# ------------------------------------------------------------
# TEST 6: LUT-to-LUT registered pipeline
# ------------------------------------------------------------

@cocotb.test()
async def test_lut_pipeline(dut):

    await start(dut)

    # LUT0 registers ui_in[0].
    # LUT1 registers LUT0's registered output.

    luts = [
        0xAAAA,
        0xAAAA,
        0x0000,
        0x0000
    ]

    routes = [
        [0, R_0, R_0, R_0],
        [R_Q[0], R_0, R_0, R_0],
        [R_0, R_0, R_0, R_0],
        [R_0, R_0, R_0, R_0]
    ]

    await configure(
        dut,
        luts,
        routes,
        reg_mode=0x3
    )

    dut.ui_in.value = 1

    await cycles(dut, 3)

    assert (read_output(dut) & 0x2) == 0x2

    dut.ui_in.value = 0

    await cycles(dut, 3)

    assert (read_output(dut) & 0x2) == 0

    dut._log.info("PASS: LUT pipeline")


# ------------------------------------------------------------
# TEST 7: Invalid configuration lengths
# ------------------------------------------------------------

@cocotb.test()
async def test_bad_length_rejected(dut):

    await start(dut)

    luts = [0xFFFF] * 4

    routes = [
        [R_1, R_1, R_1, R_1]
        for _ in range(4)
    ]

    cfg = build_cfg(luts, routes)

    # 131-bit configuration must be rejected.
    await spi_write(dut, cfg, 131)

    assert read_output(dut) == 0

    # 133-bit configuration must be rejected.
    await spi_write(dut, cfg, 133)

    assert read_output(dut) == 0

    # Exactly 132 bits must be accepted.
    await spi_write(dut, cfg, 132)

    await cycles(dut, 3)

    assert read_output(dut) == 0xF

    dut._log.info("PASS: configuration length validation")


# ------------------------------------------------------------
# TEST 8: Live reconfiguration
# ------------------------------------------------------------

@cocotb.test()
async def test_reconfiguration(dut):

    await start(dut)

    routes = [
        [0, 1, R_0, R_0]
        for _ in range(4)
    ]

    # Configure all LUTs as AND.
    await configure(
        dut,
        [0x0008] * 4,
        routes
    )

    dut.ui_in.value = 0b11

    await cycles(dut, 2)

    assert read_output(dut) == 0xF

    # Reconfigure all LUTs as OR.
    await configure(
        dut,
        [0x000E] * 4,
        routes
    )

    dut.ui_in.value = 0b01

    await cycles(dut, 2)

    assert read_output(dut) == 0xF

    dut._log.info("PASS: live reconfiguration")
