`default_nettype none

module tinyfpga (
    input  logic       clk,
    input  logic       rst_n,

    // SPI Mode 0, MSB first
    input  logic       spi_sclk,
    input  logic       spi_cs_n,
    input  logic       spi_mosi,
    output logic       spi_miso,

    // Fabric I/O
    input  logic [7:0] io_in,
    output logic [3:0] io_out
);

    // =========================================================
    // COMPACT FPGA ARCHITECTURE
    // 4 LUT4s
    // 4 optional LUT output registers
    // 1 x 8-bit counter
    // 1 x 8-bit shift register
    // 1 PWM channel
    // =========================================================

    localparam integer CFG_BITS = 164;

    // =========================================================
    // SPI SYNCHRONIZATION
    // =========================================================

    logic [2:0] sclk_s;
    logic [2:0] cs_s;
    logic [1:0] mosi_s;

    wire sclk_rise = (sclk_s[2:1] == 2'b01);
    wire cs_active = ~cs_s[1];
    wire cs_rise   = (cs_s[2:1] == 2'b01);

    logic [CFG_BITS-1:0] cfg;
    logic [7:0] bit_cnt;
    logic cfg_valid;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            sclk_s    <= 3'b000;
            cs_s      <= 3'b111;
            mosi_s    <= 2'b00;
            cfg       <= '0;
            bit_cnt   <= 8'd0;
            cfg_valid <= 1'b0;
        end else begin

            sclk_s <= {sclk_s[1:0], spi_sclk};
            cs_s   <= {cs_s[1:0], spi_cs_n};
            mosi_s <= {mosi_s[0], spi_mosi};

            // Receive configuration bits.
            if (cs_active && sclk_rise && bit_cnt < CFG_BITS)
                cfg <= {cfg[CFG_BITS-2:0], mosi_s[1]};

            // Count all received bits.
            if (!cs_active)
                bit_cnt <= 8'd0;
            else if (sclk_rise && bit_cnt != 8'hFF)
                bit_cnt <= bit_cnt + 8'd1;

            // Disable the fabric during configuration.
            if (cs_active)
                cfg_valid <= 1'b0;

            // Accept only exactly 164 bits.
            if (cs_rise)
                cfg_valid <= (bit_cnt == CFG_BITS);

        end
    end

    assign spi_miso = 1'b0;

    // =========================================================
    // CONFIGURATION MAP: 164 BITS
    // =========================================================
    //
    // [ 63:  0] Four LUT truth tables
    // [127: 64] Sixteen 4-bit routing selectors
    // [131:128] Four LUT register modes
    //
    // [139:132] Shared counter/PWM period
    // [140]     Counter enable
    //
    // [148:141] Shift-register initial value
    // [152:149] Shift-register input selector
    // [153]     Shift-register enable
    // [154]     Shift direction
    //
    // [162:155] PWM duty cycle
    // [163]     PWM enable
    //
    // =========================================================

    wire [3:0] reg_mode = cfg[131:128];

    // =========================================================
    // FABRIC STATE
    // =========================================================

    logic [3:0] lut_q;
    wire  [3:0] lut_result;

    logic [7:0] timebase_count;
    logic       counter_tick;

    logic [7:0] shift_reg;

    wire pwm_out;

    logic cfg_valid_d;

    // =========================================================
    // ROUTING NETWORK
    // =========================================================
    //
    // 0-7  : External inputs
    // 8-11 : Registered LUT outputs
    // 12   : Counter MSB
    // 13   : Counter terminal pulse
    // 14   : Shift-register MSB
    // 15   : PWM output
    //
    // Constants can be implemented using LUT truth tables:
    // 16'h0000 = constant zero
    // 16'hFFFF = constant one
    //
    // =========================================================

    function automatic logic route_select (
        input logic [3:0] select,
        input logic [7:0] external_inputs,
        input logic [3:0] lut_outputs,
        input logic       counter_msb,
        input logic       counter_event,
        input logic       shift_msb,
        input logic       pwm_value
    );

        begin
            case (select)

                4'd0:  route_select = external_inputs[0];
                4'd1:  route_select = external_inputs[1];
                4'd2:  route_select = external_inputs[2];
                4'd3:  route_select = external_inputs[3];
                4'd4:  route_select = external_inputs[4];
                4'd5:  route_select = external_inputs[5];
                4'd6:  route_select = external_inputs[6];
                4'd7:  route_select = external_inputs[7];

                4'd8:  route_select = lut_outputs[0];
                4'd9:  route_select = lut_outputs[1];
                4'd10: route_select = lut_outputs[2];
                4'd11: route_select = lut_outputs[3];

                4'd12: route_select = counter_msb;
                4'd13: route_select = counter_event;
                4'd14: route_select = shift_msb;
                4'd15: route_select = pwm_value;

                default: route_select = 1'b0;

            endcase
        end

    endfunction

    // =========================================================
    // SHARED COUNTER / PWM TIMEBASE
    // =========================================================

    // Period = configured value + 1 clock cycles.
    // Counter and PWM share the same timebase.

    always_ff @(posedge clk) begin

        if (!rst_n || !cfg_valid) begin
            timebase_count <= 8'd0;
            counter_tick   <= 1'b0;
        end

        else if (!cfg_valid_d) begin
            timebase_count <= 8'd0;
            counter_tick   <= 1'b0;
        end

        else begin

            counter_tick <= 1'b0;

            if (cfg[140] || cfg[163]) begin

                if (timebase_count >= cfg[139:132]) begin

                    timebase_count <= 8'd0;

                    if (cfg[140])
                        counter_tick <= 1'b1;

                end else begin

                    timebase_count <= timebase_count + 8'd1;

                end

            end else begin

                timebase_count <= 8'd0;

            end

        end
    end

    // =========================================================
    // SHIFT REGISTER INPUT
    // =========================================================

    wire shift_input = route_select(
        cfg[152:149],
        io_in,
        lut_q,
        timebase_count[7],
        counter_tick,
        shift_reg[7],
        pwm_out
    );

    // =========================================================
    // ONE CONFIGURABLE 8-BIT SHIFT REGISTER
    // =========================================================

    always_ff @(posedge clk) begin

        if (!rst_n || !cfg_valid) begin

            shift_reg <= 8'd0;

        end

        else if (!cfg_valid_d) begin

            shift_reg <= cfg[148:141];

        end

        else if (cfg[153]) begin

            if (cfg[154])
                shift_reg <= {shift_input, shift_reg[7:1]};
            else
                shift_reg <= {shift_reg[6:0], shift_input};

        end

    end

    // =========================================================
    // PWM GENERATOR
    // =========================================================

    assign pwm_out =
        cfg_valid &&
        cfg[163] &&
        ((&cfg[162:155]) ||
         (timebase_count < cfg[162:155]));

    // =========================================================
    // FOUR LUT4 BLOCKS
    // =========================================================

    genvar i;
    genvar j;

    generate

        for (i = 0; i < 4; i = i + 1) begin : g_lut

            wire [3:0] lut_inputs;
            wire [15:0] truth_table;

            assign truth_table = cfg[i*16 +: 16];

            for (j = 0; j < 4; j = j + 1) begin : g_input

                assign lut_inputs[j] = route_select(
                    cfg[64 + (i*4+j)*4 +: 4],
                    io_in,
                    lut_q,
                    timebase_count[7],
                    counter_tick,
                    shift_reg[7],
                    pwm_out
                );

            end

            assign lut_result[i] = truth_table[lut_inputs];

        end

    endgenerate

    // =========================================================
    // CONFIGURATION VALID STATE
    // =========================================================

    always_ff @(posedge clk) begin

        if (!rst_n)
            cfg_valid_d <= 1'b0;
        else
            cfg_valid_d <= cfg_valid;

    end

    // =========================================================
    // OPTIONAL LUT OUTPUT REGISTERS
    // =========================================================

    always_ff @(posedge clk) begin

        if (!rst_n || !cfg_valid)
            lut_q <= 4'b0000;
        else
            lut_q <= lut_result;

    end

    // =========================================================
    // EXTERNAL OUTPUTS
    // =========================================================

    wire [3:0] fabric_result =
        (reg_mode & lut_q) |
        ((~reg_mode) & lut_result);

    assign io_out = cfg_valid ? fabric_result : 4'b0000;

endmodule

`default_nettype wire
