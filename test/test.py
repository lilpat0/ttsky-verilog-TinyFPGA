
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

CFG_BITS = 222
SPI_HALF = 4

# Routing selectors
R_Q = [8, 9, 10, 11]

R_COUNTER0 = 12
R_COUNTER1 = 13

R_SHIFT0_MSB = 14
R_SHIFT1_MSB = 15

R_PWM0 = 16
R_PWM1 = 17

R_COUNTER0_TICK = 18
R_COUNTER1_TICK = 19

R_SHIFT0_LSB = 20
R_SHIFT1_LSB = 21

R_ZERO = 0
R_ONE = 31


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


async def cycles(dut, count=1):

    for _ in range(count):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")


# ============================================================
# CONFIGURATION BUILDER
# ============================================================

def build_cfg(
    luts,
    routes,
    reg_mode=0,

    counter0_period=1,
    counter0_enable=0,

    counter1_period=1,
    counter1_enable=0,

    shift0_init=0,
    shift0_input=0,
    shift0_enable=0,
    shift0_dir=0,

    shift1_init=0,
    shift1_input=0,
    shift1_enable=0,
    shift1_dir=0,

    pwm_period=9,

    pwm0_duty=0,
    pwm0_enable=0,

    pwm1_duty=0,
    pwm1_enable=0
):

    assert len(luts) == 4
    assert len(routes) == 4

    cfg = 0

    # --------------------------------------------------------
    # LUT TRUTH TABLES [63:0]
    # --------------------------------------------------------

    for i in range(4):

        assert 0 <= luts[i] <= 0xFFFF

        cfg |= (luts[i] & 0xFFFF) << (i * 16)

    # --------------------------------------------------------
    # LUT ROUTING [143:64]
    # 16 selectors, 5 bits each
    # --------------------------------------------------------

    for i in range(4):

        assert len(routes[i]) == 4

        for j in range(4):

            route = routes[i][j]

            assert 0 <= route <= 31

            position = 64 + (i * 4 + j) * 5

            cfg |= (route & 0x1F) << position

    # --------------------------------------------------------
    # LUT REGISTER MODES [147:144]
    # --------------------------------------------------------

    cfg |= (reg_mode & 0xF) << 144

    # --------------------------------------------------------
    # COUNTER 0 [156:148]
    # --------------------------------------------------------

    assert 0 <= counter0_period <= 255

    cfg |= (counter0_period & 0xFF) << 148
    cfg |= (counter0_enable & 1) << 156

    # --------------------------------------------------------
    # COUNTER 1 [165:157]
    # --------------------------------------------------------

    assert 0 <= counter1_period <= 255

    cfg |= (counter1_period & 0xFF) << 157
    cfg |= (counter1_enable & 1) << 165

    # --------------------------------------------------------
    # SHIFT REGISTER 0 [180:166]
    # --------------------------------------------------------

    cfg |= (shift0_init & 0xFF) << 166
    cfg |= (shift0_input & 0x1F) << 174
    cfg |= (shift0_enable & 1) << 179
    cfg |= (shift0_dir & 1) << 180

    # --------------------------------------------------------
    # SHIFT REGISTER 1 [195:181]
    # --------------------------------------------------------

    cfg |= (shift1_init & 0xFF) << 181
    cfg |= (shift1_input & 0x1F) << 189
    cfg |= (shift1_enable & 1) << 194
    cfg |= (shift1_dir & 1) << 195

    # --------------------------------------------------------
    # PWM PERIOD [203:196]
    # --------------------------------------------------------

    cfg |= (pwm_period & 0xFF) << 196

    # --------------------------------------------------------
    # PWM 0 [212:204]
    # --------------------------------------------------------

    cfg |= (pwm0_duty & 0xFF) << 204
    cfg |= (pwm0_enable & 1) << 212

    # --------------------------------------------------------
    # PWM 1 [221:213]
    # --------------------------------------------------------

    cfg |= (pwm1_duty & 0xFF) << 213
    cfg |= (pwm1_enable & 1) << 221

    assert cfg.bit_length() <= CFG_BITS

    return cfg


# ============================================================
# SPI MODE 0, MSB FIRST
# ============================================================

async def spi_write(dut, value, nbits=CFG_BITS):

    assert 0 < nbits <= 255

    set_spi_pins(dut, sclk=0, cs_n=0, mosi=0)

    await cycles(dut, 8)

    for bit in range(nbits - 1, -1, -1):

        mosi = (value >> bit) & 1

        # Data stable before rising edge
        set_spi_pins(
            dut,
            sclk=0,
            cs_n=0,
            mosi=mosi
        )

        await cycles(dut, SPI_HALF)

        # Sampling edge
        set_spi_pins(
            dut,
            sclk=1,
            cs_n=0,
            mosi=mosi
        )

        await cycles(dut, SPI_HALF)

        # Return clock low
        set_spi_pins(
            dut,
            sclk=0,
            cs_n=0,
            mosi=mosi
        )

    await cycles(dut, 8)

    # End transaction
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

    cocotb.start_soon(
        Clock(dut.clk, 10, unit="ns").start()
    )

    await cycles(dut, 5)

    dut.rst_n.value = 1

    await cycles(dut, 10)


async def configure(
    dut,
    luts,
    routes,
    reg_mode=0,
    **kwargs
):

    cfg = build_cfg(
        luts,
        routes,
        reg_mode,
        **kwargs
    )

    await spi_write(dut, cfg)

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

    dut._log.info("PASS: reset and TinyTapeout pin mapping")


# ============================================================
# TEST 2: LUT FUNCTIONALITY
# ============================================================

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
        [0, 1, 0, 0],
        [0, 1, 0, 0],
        [0, 1, 0, 0],
        [0, 0, 0, 0]
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


# ============================================================
# TEST 3: CONSTANT ROUTING
# ============================================================

@cocotb.test()
async def test_constants(dut):

    await start(dut)

    # LUT0 and LUT2 receive constant 1.
    # LUT1 and LUT3 receive constant 0.

    luts = [0xAAAA] * 4

    routes = [
        [R_ONE, 0, 0, 0],
        [0, 0, 0, 0],
        [R_ONE, 0, 0, 0],
        [0, 0, 0, 0]
    ]

    await configure(dut, luts, routes)

    dut.ui_in.value = 0

    await cycles(dut, 3)

    result = read_output(dut)

    expected = 0b0101

    assert result == expected, (
        f"Expected={expected:04b}, Got={result:04b}"
    )

    dut._log.info("PASS: constant routing")


# ============================================================
# TEST 4: REGISTERED OUTPUTS
# ============================================================

@cocotb.test()
async def test_registered_outputs(dut):

    await start(dut)

    luts = [0xAAAA] * 4

    routes = [
        [0, 0, 0, 0]
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

    await Timer(1, unit="ns")

    assert read_output(dut) == 0xF

    await cycles(dut, 1)

    assert read_output(dut) == 0

    dut._log.info("PASS: registered outputs")


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
        [R_Q[0], 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0]
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


# ============================================================
# TEST 6: LUT-TO-LUT PIPELINE
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
        [0, 0, 0, 0],
        [R_Q[0], 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0]
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


# ============================================================
# TEST 7: CONFIGURABLE COUNTERS
# ============================================================

@cocotb.test()
async def test_counters(dut):

    await start(dut)

    # LUT0 exposes counter 0 terminal pulse.
    # LUT1 exposes counter 1 terminal pulse.

    luts = [0xAAAA] * 4

    routes = [
        [R_COUNTER0_TICK, 0, 0, 0],
        [R_COUNTER1_TICK, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0]
    ]

    await configure(
        dut,
        luts,
        routes,

        counter0_period=3,
        counter0_enable=1,

        counter1_period=5,
        counter1_enable=1
    )

    count0 = 0
    count1 = 0

    # 15 cycles = five periods of counter 0
    # and three periods of counter 1.

    for _ in range(15):

        await cycles(dut, 1)

        result = read_output(dut)

        count0 += (result >> 0) & 1
        count1 += (result >> 1) & 1

    assert count0 == 5, (
        f"Counter 0 expected 5 pulses, got {count0}"
    )

    assert count1 == 3, (
        f"Counter 1 expected 3 pulses, got {count1}"
    )

    dut._log.info("PASS: both configurable counters")


# ============================================================
# TEST 8: SHIFT REGISTERS
# ============================================================

@cocotb.test()
async def test_shift_registers(dut):

    await start(dut)

    # LUT0 exposes shift register 0 MSB.
    # LUT1 exposes shift register 1 MSB.

    luts = [0xAAAA] * 4

    routes = [
        [R_SHIFT0_MSB, 0, 0, 0],
        [R_SHIFT1_MSB, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0]
    ]

    await configure(
        dut,
        luts,
        routes,

        shift0_init=0x00,
        shift0_input=0,
        shift0_enable=1,
        shift0_dir=0,

        shift1_init=0x00,
        shift1_input=1,
        shift1_enable=1,
        shift1_dir=1
    )

    # Both input sources receive logic 1.
    dut.ui_in.value = 0b00000011

    await cycles(dut, 8)

    result = read_output(dut)

    assert (result & 0x3) == 0x3, (
        f"Expected both shift register MSBs high, "
        f"got {result:04b}"
    )

    dut._log.info("PASS: both shift registers")


# ============================================================
# TEST 9: PWM GENERATORS
# ============================================================

@cocotb.test()
async def test_pwm(dut):

    await start(dut)

    # LUT0 exposes PWM0.
    # LUT1 exposes PWM1.

    luts = [0xAAAA] * 4

    routes = [
        [R_PWM0, 0, 0, 0],
        [R_PWM1, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0]
    ]

    await configure(
        dut,
        luts,
        routes,

        pwm_period=9,

        pwm0_duty=4,
        pwm0_enable=1,

        pwm1_duty=7,
        pwm1_enable=1
    )

    high0 = 0
    high1 = 0

    # Period = 9 means a 10-clock PWM period.
    # Duty 4 = four high clocks.
    # Duty 7 = seven high clocks.

    for _ in range(10):

        await cycles(dut, 1)

        result = read_output(dut)

        high0 += (result >> 0) & 1
        high1 += (result >> 1) & 1

    assert high0 == 4, (
        f"PWM0 expected 4 high cycles, got {high0}"
    )

    assert high1 == 7, (
        f"PWM1 expected 7 high cycles, got {high1}"
    )

    dut._log.info("PASS: both PWM channels")


# ============================================================
# TEST 10: INVALID CONFIGURATION LENGTHS
# ============================================================

@cocotb.test()
async def test_bad_length_rejected(dut):

    await start(dut)

    luts = [0xFFFF] * 4

    routes = [
        [0, 0, 0, 0]
        for _ in range(4)
    ]

    cfg = build_cfg(luts, routes)

    # 221-bit configuration must be rejected.
    await spi_write(dut, cfg, 221)

    assert read_output(dut) == 0

    # 223-bit configuration must be rejected.
    await spi_write(dut, cfg, 223)

    assert read_output(dut) == 0

    # Exactly 222 bits must be accepted.
    await spi_write(dut, cfg, 222)

    await cycles(dut, 3)

    assert read_output(dut) == 0xF

    dut._log.info("PASS: configuration length validation")


# ============================================================
# TEST 11: LIVE RECONFIGURATION
# ============================================================

@cocotb.test()
async def test_reconfiguration(dut):

    await start(dut)

    routes = [
        [0, 1, 0, 0]
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
