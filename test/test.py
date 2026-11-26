
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

CFG_BITS = 132
SPI_HALF = 4

# Routing selector values
R_IN = list(range(8))
R_Q = [8, 9, 10, 11]
R_0 = 12
R_1 = 13

# ------------------------------------------------------------
# Clock helpers
# ------------------------------------------------------------

async def cycles(dut, count=1):
    for _ in range(count):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")


async def after_edge(dut):
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


# ------------------------------------------------------------
# Configuration builder
# ------------------------------------------------------------

def build_cfg(luts, routes, reg_mode=0):
    """
    Build 132-bit configuration.

    luts:
        Four 16-bit LUT truth tables.

    routes:
        Four lists, each containing four routing selectors.

    reg_mode:
        Four-bit output register enable mask.
    """

    assert len(luts) == 4
    assert len(routes) == 4

    cfg = 0

    # LUT truth tables [63:0]
    for i in range(4):
        assert 0 <= luts[i] <= 0xFFFF
        cfg |= (luts[i] & 0xFFFF) << (i * 16)

    # Routing selectors [127:64]
    for i in range(4):
        assert len(routes[i]) == 4

        for j in range(4):
            route = routes[i][j]
            assert 0 <= route <= 15

            position = 64 + (i * 4 + j) * 4
            cfg |= (route & 0xF) << position

    # Register mode [131:128]
    cfg |= (reg_mode & 0xF) << 128

    return cfg


# ------------------------------------------------------------
# SPI writer
# ------------------------------------------------------------

async def spi_write(dut, value, nbits=CFG_BITS):
    """
    SPI Mode 0, MSB first.

    The DUT synchronizes SPI signals to clk.
    """

    assert nbits > 0

    dut.spi_cs_n.value = 0
    dut.spi_sclk.value = 0

    await cycles(dut, 8)

    for bit in range(nbits - 1, -1, -1):

        dut.spi_mosi.value = (value >> bit) & 1

        await cycles(dut, SPI_HALF)

        # Rising edge: DUT samples MOSI
        dut.spi_sclk.value = 1
        await cycles(dut, SPI_HALF)

        # Falling edge
        dut.spi_sclk.value = 0

    await cycles(dut, 8)

    # End transaction
    dut.spi_cs_n.value = 1
    dut.spi_mosi.value = 0

    # Allow synchronized CS rising edge to be detected
    await cycles(dut, 10)


# ------------------------------------------------------------
# Reset and initialization
# ------------------------------------------------------------

async def start(dut):

    dut.spi_sclk.value = 0
    dut.spi_cs_n.value = 1
    dut.spi_mosi.value = 0

    dut.io_in.value = 0

    dut.rst_n.value = 0

    cocotb.start_soon(
        Clock(dut.clk, 10, unit="ns").start()
    )

    await cycles(dut, 5)

    dut.rst_n.value = 1

    await cycles(dut, 10)


# ------------------------------------------------------------
# Read outputs
# ------------------------------------------------------------

async def read_output(dut):
    await Timer(1, unit="ns")
    return int(dut.io_out.value)


async def configure(dut, luts, routes, reg_mode=0):
    cfg = build_cfg(luts, routes, reg_mode)
    await spi_write(dut, cfg)
    await cycles(dut, 3)


# ------------------------------------------------------------
# Test 1: Reset and SPI pin behavior
# ------------------------------------------------------------

@cocotb.test()
async def test_reset(dut):

    await start(dut)

    assert int(dut.io_out.value) == 0
    assert int(dut.spi_miso.value) == 0

    dut._log.info("PASS: Reset and SPI output")


# ------------------------------------------------------------
# Test 2: LUT functionality
# ------------------------------------------------------------

@cocotb.test()
async def test_lut_logic(dut):

    await start(dut)

    # LUT0 = AND
    # LUT1 = XOR
    # LUT2 = OR
    # LUT3 = NOT input 0

    luts = [
        0x8000,
        0x6996,
        0xFFFE,
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

        dut.io_in.value = value

        await cycles(dut, 2)

        result = await read_output(dut)

        a = (value >> 0) & 1
        b = (value >> 1) & 1

        expected0 = a & b
        expected1 = a ^ b
        expected2 = a | b
        expected3 = 1 - a

        expected = (
            expected0 |
            (expected1 << 1) |
            (expected2 << 2) |
            (expected3 << 3)
        )

        assert result == expected, (
            f"LUT failure: io_in={value:02X}, "
            f"expected={expected:04b}, "
            f"got={result:04b}"
        )

    dut._log.info("PASS: All 256 input patterns")


# ------------------------------------------------------------
# Test 3: Constant routing
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

    dut.io_in.value = 0x00

    await cycles(dut, 3)

    result = await read_output(dut)

    # LUT0: index 15 -> 1
    # LUT1: index 0  -> 1
    # LUT2: index 0  -> 1
    # LUT3: index 8  -> 0

    expected = 0b0111

    assert result == expected, (
        f"Constant routing failure: "
        f"expected={expected:04b}, got={result:04b}"
    )

    dut._log.info("PASS: Constant routing")


# ------------------------------------------------------------
# Test 4: Registered outputs
# ------------------------------------------------------------

@cocotb.test()
async def test_registered_outputs(dut):

    await start(dut)

    # Four LUTs configured as direct input 0
    luts = [0xAAAA] * 4

    routes = [
        [0, R_0, R_0, R_0],
        [0, R_0, R_0, R_0],
        [0, R_0, R_0, R_0],
        [0, R_0, R_0, R_0]
    ]

    # All four outputs registered
    await configure(dut, luts, routes, reg_mode=0xF)

    dut.io_in.value = 1

    await cycles(dut, 2)

    result = await read_output(dut)

    assert result == 0xF, (
        f"Registered output failed: got {result:04b}"
    )

    dut.io_in.value = 0

    # Output remains high until next clock
    result = await read_output(dut)

    assert result == 0xF, (
        "Registered output changed without a clock edge"
    )

    await cycles(dut, 1)

    result = await read_output(dut)

    assert result == 0x0, (
        "Registered output did not update after clock"
    )

    dut._log.info("PASS: Registered outputs")


# ------------------------------------------------------------
# Test 5: LUT feedback
# ------------------------------------------------------------

@cocotb.test()
async def test_lut_feedback(dut):

    await start(dut)

    # LUT0 = NOT its own registered output
    #
    # When reg_mode[0] is enabled:
    # lut_q[0] <= ~lut_q[0]
    #
    # Expected behavior: toggles every clock.

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

    await configure(dut, luts, routes, reg_mode=0x1)

    previous = 0

    for _ in range(10):

        await cycles(dut, 1)

        result = await read_output(dut) & 1

        assert result != previous, (
            "Feedback oscillator did not toggle"
        )

        previous = result

    dut._log.info("PASS: LUT feedback")


# ------------------------------------------------------------
# Test 6: LUT-to-LUT registered pipeline
# ------------------------------------------------------------

@cocotb.test()
async def test_lut_pipeline(dut):

    await start(dut)

    # LUT0 = io_in[0]
    # LUT1 = registered LUT0 output
    #
    # LUT1 uses route selector 8 (lut_q[0]).

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

    await configure(dut, luts, routes, reg_mode=0x2)

    dut.io_in.value = 1

    await cycles(dut, 2)

    result = await read_output(dut)

    assert (result & 0x2) == 0x2, (
        "LUT pipeline failed to propagate logic 1"
    )

    dut.io_in.value = 0

    await cycles(dut, 2)

    result = await read_output(dut)

    assert (result & 0x2) == 0, (
        "LUT pipeline failed to propagate logic 0"
    )

    dut._log.info("PASS: LUT pipeline")


# ------------------------------------------------------------
# Test 7: Invalid configuration lengths
# ------------------------------------------------------------

@cocotb.test()
async def test_bad_length_rejected(dut):

    await start(dut)

    luts = [0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF]

    routes = [
        [R_1, R_1, R_1, R_1],
        [R_1, R_1, R_1, R_1],
        [R_1, R_1, R_1, R_1],
        [R_1, R_1, R_1, R_1]
    ]

    cfg = build_cfg(luts, routes)

    # 131 bits must be rejected
    await spi_write(dut, cfg, 131)

    assert int(dut.io_out.value) == 0, (
        "131-bit configuration was incorrectly accepted"
    )

    # 133 bits must be rejected
    await spi_write(dut, cfg, 133)

    assert int(dut.io_out.value) == 0, (
        "133-bit configuration was incorrectly accepted"
    )

    # Exactly 132 bits must be accepted
    await spi_write(dut, cfg, 132)

    assert int(dut.io_out.value) == 0xF, (
        "Valid 132-bit configuration was rejected"
    )

    dut._log.info("PASS: Configuration length validation")


# ------------------------------------------------------------
# Test 8: Reconfiguration
# ------------------------------------------------------------

@cocotb.test()
async def test_reconfiguration(dut):

    await start(dut)

    routes = [
        [0, 1, R_0, R_0],
        [0, 1, R_0, R_0],
        [0, 1, R_0, R_0],
        [0, 1, R_0, R_0]
    ]

    # Configure all LUTs as AND
    await configure(
        dut,
        [0x8000] * 4,
        routes
    )

    dut.io_in.value = 0b11

    await cycles(dut, 2)

    result = await read_output(dut)

    assert result == 0xF, (
        "Initial AND configuration failed"
    )

    # Reconfigure all LUTs as OR
    await configure(
        dut,
        [0xFFFE] * 4,
        routes
    )

    dut.io_in.value = 0b01

    await cycles(dut, 2)

    result = await read_output(dut)

    assert result == 0xF, (
        "Reconfiguration to OR failed"
    )

    dut._log.info("PASS: Reconfiguration")


# ------------------------------------------------------------
# Test 9: Outputs disabled during configuration
# ------------------------------------------------------------

@cocotb.test()
async def test_outputs_disabled_during_spi(dut):

    await start(dut)

    luts = [0xFFFF] * 4

    routes = [
        [R_1, R_1, R_1, R_1],
        [R_1, R_1, R_1, R_1],
        [R_1, R_1, R_1, R_1],
        [R_1, R_1, R_1, R_1]
    ]

    await configure(dut, luts, routes)

    assert int(dut.io_out.value) == 0xF

    # Start a new SPI transaction.
    dut.spi_cs_n.value = 0
    dut.spi_sclk.value = 0

    await cycles(dut, 8)

    # Outputs must be disabled during programming.
    assert int(dut.io_out.value) == 0, (
        "Outputs were not disabled during configuration"
    )

    # Send a new valid configuration.
    cfg = build_cfg(luts, routes)

    for bit in range(CFG_BITS - 1, -1, -1):

        dut.spi_mosi.value = (cfg >> bit) & 1

        await cycles(dut, SPI_HALF)

        dut.spi_sclk.value = 1
        await cycles(dut, SPI_HALF)

        dut.spi_sclk.value = 0

    await cycles(dut, 8)

    dut.spi_cs_n.value = 1

    await cycles(dut, 10)

    assert int(dut.io_out.value) == 0xF, (
        "Outputs did not reactivate after valid configuration"
    )

    dut._log.info("PASS: Outputs disabled during SPI programming")
