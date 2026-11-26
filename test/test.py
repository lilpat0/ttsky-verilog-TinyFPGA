
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

CFG_BITS = 164
CLOCK_PERIOD_NS = 100
SETTLE_NS = 10
SPI_HALF = 4

# ============================================================
# ROUTING SELECTORS
# ============================================================

R_EXT0 = 0
R_EXT1 = 1
R_EXT2 = 2
R_EXT3 = 3
R_EXT4 = 4
R_EXT5 = 5
R_EXT6 = 6
R_EXT7 = 7

R_Q = [8, 9, 10, 11]

R_COUNTER_MSB = 12
R_COUNTER_TICK = 13
R_SHIFT_MSB = 14
R_PWM = 15


# ============================================================
# TINY TAPEOUT PIN HELPERS
# ============================================================

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


# ============================================================
# CLOCK AND SETTLING
# ============================================================

async def cycles(dut, count=1):
    for _ in range(count):
        await RisingEdge(dut.clk)
        await Timer(SETTLE_NS, unit="ns")


# ============================================================
# CONFIGURATION BUILDER
# ============================================================

def build_cfg(
    luts,
    routes,
    reg_mode=0,
    counter_period=3,
    counter_enable=0,
    shift_init=0,
    shift_input=R_EXT0,
    shift_enable=0,
    shift_dir=0,
    pwm_duty=0,
    pwm_enable=0
):

    assert len(luts) == 4
    assert len(routes) == 4

    cfg = 0

    # Four LUT truth tables [63:0]
    for i, truth_table in enumerate(luts):
        assert 0 <= truth_table <= 0xFFFF
        cfg |= truth_table << (16 * i)

    # Sixteen 4-bit routing selectors [127:64]
    for i, lut_routes in enumerate(routes):
        assert len(lut_routes) == 4

        for j, selector in enumerate(lut_routes):
            assert 0 <= selector <= 15
            position = 64 + (i * 4 + j) * 4
            cfg |= selector << position

    # Register modes [131:128]
    assert 0 <= reg_mode <= 0xF
    cfg |= reg_mode << 128

    # Counter period [139:132]
    # Counter enable [140]
    assert 0 <= counter_period <= 255
    assert counter_enable in (0, 1)

    cfg |= counter_period << 132
    cfg |= counter_enable << 140

    # Shift register initial value [148:141]
    # Shift input selector [152:149]
    # Shift enable [153]
    # Shift direction [154]
    assert 0 <= shift_init <= 255
    assert 0 <= shift_input <= 15
    assert shift_enable in (0, 1)
    assert shift_dir in (0, 1)

    cfg |= shift_init << 141
    cfg |= shift_input << 149
    cfg |= shift_enable << 153
    cfg |= shift_dir << 154

    # PWM duty [162:155]
    # PWM enable [163]
    assert 0 <= pwm_duty <= 255
    assert pwm_enable in (0, 1)

    cfg |= pwm_duty << 155
    cfg |= pwm_enable << 163

    assert cfg.bit_length() <= CFG_BITS

    return cfg


# ============================================================
# SPI MODE 0, MSB FIRST
# ============================================================

async def spi_write(dut, value, nbits=CFG_BITS):

    assert 0 < nbits <= 255
    assert value >= 0

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

    # End configuration transaction
    set_spi_pins(dut, sclk=0, cs_n=1, mosi=0)

    await cycles(dut, 10)


# ============================================================
# RESET AND INITIALIZATION
# ============================================================

async def start(dut):

    dut.clk.value = 0
    dut.rst_n.value = 0
    dut.ena.value = 1
    dut.ui_in.value = 0

    set_spi_pins(dut)

    # Match config.yaml: 100 ns = 10 MHz
    cocotb.start_soon(
        Clock(
            dut.clk,
            CLOCK_PERIOD_NS,
            unit="ns"
        ).start()
    )

    await cycles(dut, 5)

    dut.rst_n.value = 1

    await cycles(dut, 10)


async def configure(dut, luts, routes, reg_mode=0, **kwargs):

    cfg = build_cfg(
        luts,
        routes,
        reg_mode,
        **kwargs
    )

    await spi_write(dut, cfg, CFG_BITS)

    await cycles(dut, 3)


# ============================================================
# TEST 1: RESET AND PIN MAPPING
# ============================================================

@cocotb.test()
async def test_reset(dut):

    await start(dut)

    assert read_output(dut) == 0
    assert read_miso(dut) == 0
    assert int(dut.uio_oe.value) == 0x08

    dut._log.info(
        "PASS: reset and TinyTapeout pin mapping"
    )


# ============================================================
# TEST 2: FOUR LUT FUNCTIONS
# ============================================================

@cocotb.test()
async def test_lut_logic(dut):

    await start(dut)

    # LUT0 = A AND B
    # LUT1 = A XOR B
    # LUT2 = A OR B
    # LUT3 = NOT A

    luts = [
        0x8888,
        0x6666,
        0xEEEE,
        0x5555
    ]

    routes = [
        [R_EXT0, R_EXT1, R_EXT0, R_EXT1],
        [R_EXT0, R_EXT1, R_EXT0, R_EXT1],
        [R_EXT0, R_EXT1, R_EXT0, R_EXT1],
        [R_EXT0, R_EXT1, R_EXT0, R_EXT1]
    ]

    await configure(dut, luts, routes)

    for value in range(256):

        dut.ui_in.value = value

        await cycles(dut, 2)

        a = value & 1
        b = (value >> 1) & 1

        expected = (
            (a & b)
            | ((a ^ b) << 1)
            | ((a | b) << 2)
            | ((1 - a) << 3)
        )

        result = read_output(dut)

        assert result == expected, (
            f"Input={value:02X}, "
            f"Expected={expected:04b}, "
            f"Got={result:04b}"
        )

    dut._log.info(
        "PASS: all 256 input combinations"
    )


# ============================================================
# TEST 3: CONSTANT LUT OUTPUTS
# ============================================================

@cocotb.test()
async def test_constants(dut):

    await start(dut)

    luts = [
        0xFFFF,
        0x0000,
        0xFFFF,
        0x0000
    ]

    routes = [
        [R_EXT0, R_EXT1, R_EXT0, R_EXT1]
        for _ in range(4)
    ]

    await configure(dut, luts, routes)

    dut.ui_in.value = 0xA5

    await cycles(dut, 3)

    assert read_output(dut) == 0b0101

    dut._log.info(
        "PASS: constant LUT outputs"
    )


# ============================================================
# TEST 4: REGISTERED OUTPUTS
# ============================================================

@cocotb.test()
async def test_registered_outputs(dut):

    await start(dut)

    luts = [0xAAAA] * 4

    routes = [
        [R_EXT0, R_EXT1, R_EXT0, R_EXT1]
        for _ in range(4)
    ]

    await configure(
        dut,
        luts,
        routes,
        reg_mode=0xF
    )

    # Drive input high
    dut.ui_in.value = 1

    await cycles(dut, 3)

    assert read_output(dut) == 0xF

    # Change input without a clock edge
    dut.ui_in.value = 0

    await Timer(10, unit="ns")

    # Registered outputs must hold their previous state
    assert read_output(dut) == 0xF

    # Allow multiple clock edges for GL settling
    await cycles(dut, 3)

    assert read_output(dut) == 0, (
        f"Registered output failed to update: "
        f"Got {read_output(dut):04b}"
    )

    dut._log.info(
        "PASS: registered output behavior"
    )


# ============================================================
# TEST 5: LUT FEEDBACK
# ============================================================

@cocotb.test()
async def test_lut_feedback(dut):

    await start(dut)

    luts = [
        0x5555,
        0x0000,
        0x0000,
        0x0000
    ]

    routes = [
        [R_Q[0], R_EXT0, R_EXT0, R_EXT0],
        [R_EXT0, R_EXT0, R_EXT0, R_EXT0],
        [R_EXT0, R_EXT0, R_EXT0, R_EXT0],
        [R_EXT0, R_EXT0, R_EXT0, R_EXT0]
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

    dut._log.info(
        "PASS: LUT feedback"
    )


# ============================================================
# TEST 6: LUT-TO-LUT REGISTERED PIPELINE
# ============================================================

@cocotb.test()
async def test_lut_pipeline(dut):

    await start(dut)

    luts = [
        0xAAAA,
        0xAAAA,
        0x0000,
        0x0000
    ]

    routes = [
        [R_EXT0, R_EXT1, R_EXT0, R_EXT1],
        [R_Q[0], R_EXT1, R_Q[0], R_EXT1],
        [R_EXT0, R_EXT1, R_EXT0, R_EXT1],
        [R_EXT0, R_EXT1, R_EXT0, R_EXT1]
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

    dut._log.info(
        "PASS: LUT pipeline"
    )


# ============================================================
# TEST 7: CONFIGURABLE COUNTER
# ============================================================

@cocotb.test()
async def test_counter(dut):

    await start(dut)

    luts = [0xAAAA] * 4

    routes = [
        [R_COUNTER_TICK, R_EXT0, R_EXT0, R_EXT0],
        [R_COUNTER_MSB, R_EXT0, R_EXT0, R_EXT0],
        [R_EXT0, R_EXT0, R_EXT0, R_EXT0],
        [R_EXT0, R_EXT0, R_EXT0, R_EXT0]
    ]

    await configure(
        dut,
        luts,
        routes,
        counter_period=3,
        counter_enable=1
    )

    pulses = 0

    for _ in range(16):

        await cycles(dut, 1)

        pulses += read_output(dut) & 1

    assert pulses == 4, (
        f"Expected 4 counter pulses, got {pulses}"
    )

    dut._log.info(
        "PASS: configurable counter"
    )


# ============================================================
# TEST 8: CONFIGURABLE SHIFT REGISTER
# ============================================================

@cocotb.test()
async def test_shift_register(dut):

    await start(dut)

    luts = [0xAAAA] * 4

    routes = [
        [R_SHIFT_MSB, R_EXT0, R_EXT0, R_EXT0],
        [R_EXT0, R_EXT0, R_EXT0, R_EXT0],
        [R_EXT0, R_EXT0, R_EXT0, R_EXT0],
        [R_EXT0, R_EXT0, R_EXT0, R_EXT0]
    ]

    await configure(
        dut,
        luts,
        routes,
        shift_init=0x00,
        shift_input=R_EXT0,
        shift_enable=1,
        shift_dir=0
    )

    dut.ui_in.value = 1

    # Eight clock edges are required to fill the register.
    # Additional edges provide margin for the GL model.
    await cycles(dut, 12)

    result = read_output(dut)

    assert (result & 1) == 1, (
        f"Shift register MSB expected 1, "
        f"got {result:04b}"
    )

    dut._log.info(
        "PASS: configurable shift register"
    )


# ============================================================
# TEST 9: CONFIGURABLE PWM
# ============================================================

@cocotb.test()
async def test_pwm(dut):

    await start(dut)

    luts = [0xAAAA] * 4

    routes = [
        [R_PWM, R_EXT0, R_EXT0, R_EXT0],
        [R_EXT0, R_EXT0, R_EXT0, R_EXT0],
        [R_EXT0, R_EXT0, R_EXT0, R_EXT0],
        [R_EXT0, R_EXT0, R_EXT0, R_EXT0]
    ]

    await configure(
        dut,
        luts,
        routes,
        counter_period=9,
        pwm_duty=4,
        pwm_enable=1
    )

    high_cycles = 0

    for _ in range(10):

        await cycles(dut, 1)

        high_cycles += read_output(dut) & 1

    assert high_cycles == 4, (
        f"PWM expected 4 high clocks, "
        f"got {high_cycles}"
    )

    dut._log.info(
        "PASS: configurable PWM"
    )


# ============================================================
# TEST 10: INVALID CONFIGURATION LENGTHS
# ============================================================

@cocotb.test()
async def test_bad_length_rejected(dut):

    await start(dut)

    luts = [0xFFFF] * 4

    routes = [
        [R_EXT0, R_EXT1, R_EXT0, R_EXT1]
        for _ in range(4)
    ]

    cfg = build_cfg(luts, routes)

    # 163-bit configuration must be rejected.
    await spi_write(dut, cfg, 163)

    assert read_output(dut) == 0

    # 165-bit configuration must be rejected.
    await spi_write(dut, cfg, 165)

    assert read_output(dut) == 0

    # Exactly 164 bits must be accepted.
    await spi_write(dut, cfg, 164)

    await cycles(dut, 3)

    assert read_output(dut) == 0xF

    dut._log.info(
        "PASS: configuration length validation"
    )


# ============================================================
# TEST 11: LIVE RECONFIGURATION
# ============================================================

@cocotb.test()
async def test_reconfiguration(dut):

    await start(dut)

    routes = [
        [R_EXT0, R_EXT1, R_EXT0, R_EXT1]
        for _ in range(4)
    ]

    # First configuration: AND
    await configure(
        dut,
        [0x8888] * 4,
        routes
    )

    dut.ui_in.value = 0b00000011

    await cycles(dut, 3)

    assert read_output(dut) == 0xF

    # Second configuration: OR
    await configure(
        dut,
        [0xEEEE] * 4,
        routes
    )

    dut.ui_in.value = 0b00000001

    await cycles(dut, 3)

    assert read_output(dut) == 0xF

    dut._log.info(
        "PASS: live reconfiguration"
    )
