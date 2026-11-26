
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

    localparam integer CFG_BITS = 222;

    // =========================================================
    // SPI CONFIGURATION
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

            if (cs_active && sclk_rise && bit_cnt < CFG_BITS)
                cfg <= {cfg[CFG_BITS-2:0], mosi_s[1]};

            if (!cs_active)
                bit_cnt <= 8'd0;
            else if (sclk_rise && bit_cnt != 8'hFF)
                bit_cnt <= bit_cnt + 8'd1;

            if (cs_active)
                cfg_valid <= 1'b0;

            if (cs_rise)
                cfg_valid <= (bit_cnt == CFG_BITS);

        end
    end

    assign spi_miso = 1'b0;

    // =========================================================
    // CONFIGURATION MAP
    // =========================================================

    // 0-63       : Four LUT4 truth tables
    // 64-143     : Sixteen 5-bit LUT routing selectors
    // 144-147    : Four LUT register modes
    //
    // 148-155    : Counter 0 period
    // 156        : Counter 0 enable
    // 157-164    : Counter 1 period
    // 165        : Counter 1 enable
    //
    // 166-173    : Shift register 0 initial value
    // 174-178    : Shift register 0 input selector
    // 179        : Shift register 0 enable
    // 180        : Shift register 0 direction
    //
    // 181-188    : Shift register 1 initial value
    // 189-193    : Shift register 1 input selector
    // 194        : Shift register 1 enable
    // 195        : Shift register 1 direction
    //
    // 196-203    : PWM shared period
    // 204-211    : PWM 0 duty cycle
    // 212        : PWM 0 enable
    // 213-220    : PWM 1 duty cycle
    // 221        : PWM 1 enable

    wire [3:0] reg_mode = cfg[147:144];

    // =========================================================
    // FABRIC RESOURCES
    // =========================================================

    logic [3:0] lut_q;
    wire  [3:0] lut_result;

    logic [7:0] counter0;
    logic [7:0] counter1;

    logic counter0_tick;
    logic counter1_tick;

    logic [7:0] shift0;
    logic [7:0] shift1;

    logic [7:0] pwm_count;

    wire pwm0;
    wire pwm1;

    // =========================================================
    // SHARED ROUTING NETWORK
    // =========================================================

    // Selector map:
    //
    //  0-7  : External inputs
    //  8-11 : LUT registered outputs
    //  12   : Counter 0 MSB
    //  13   : Counter 1 MSB
    //  14   : Shift register 0 MSB
    //  15   : Shift register 1 MSB
    //  16   : PWM 0
    //  17   : PWM 1
    //  18   : Counter 0 terminal pulse
    //  19   : Counter 1 terminal pulse
    //  20   : Shift register 0 LSB
    //  21   : Shift register 1 LSB
    //  31   : Logic 1
    //  Other : Logic 0

    function automatic logic route_select (
        input logic [4:0] select,
        input logic [7:0] external_inputs,
        input logic [3:0] internal_outputs,
        input logic c0_msb,
        input logic c1_msb,
        input logic c0_tick,
        input logic c1_tick,
        input logic s0_msb,
        input logic s1_msb,
        input logic s0_lsb,
        input logic s1_lsb,
        input logic p0,
        input logic p1
    );

        begin
            case (select)

                5'd0: route_select = external_inputs[0];
                5'd1: route_select = external_inputs[1];
                5'd2: route_select = external_inputs[2];
                5'd3: route_select = external_inputs[3];
                5'd4: route_select = external_inputs[4];
                5'd5: route_select = external_inputs[5];
                5'd6: route_select = external_inputs[6];
                5'd7: route_select = external_inputs[7];

                5'd8:  route_select = internal_outputs[0];
                5'd9:  route_select = internal_outputs[1];
                5'd10: route_select = internal_outputs[2];
                5'd11: route_select = internal_outputs[3];

                5'd12: route_select = c0_msb;
                5'd13: route_select = c1_msb;

                5'd14: route_select = s0_msb;
                5'd15: route_select = s1_msb;

                5'd16: route_select = p0;
                5'd17: route_select = p1;

                5'd18: route_select = c0_tick;
                5'd19: route_select = c1_tick;

                5'd20: route_select = s0_lsb;
                5'd21: route_select = s1_lsb;

                5'd31: route_select = 1'b1;

                default: route_select = 1'b0;

            endcase
        end

    endfunction

    // =========================================================
    // PWM GENERATORS
    // =========================================================

    // Shared programmable timebase.
    // Each PWM channel has an independent duty cycle.

    always_ff @(posedge clk) begin

        if (!rst_n || !cfg_valid) begin
            pwm_count <= 8'd0;
        end
        else if (pwm_count >= cfg[203:196]) begin
            pwm_count <= 8'd0;
        end
        else begin
            pwm_count <= pwm_count + 8'd1;
        end

    end

    assign pwm0 =
        cfg_valid &&
        cfg[212] &&
        ((cfg[211:204] == 8'hFF) ||
         (pwm_count < cfg[211:204]));

    assign pwm1 =
        cfg_valid &&
        cfg[221] &&
        ((cfg[220:213] == 8'hFF) ||
         (pwm_count < cfg[220:213]));

    // =========================================================
    // COUNTERS
    // =========================================================

    logic cfg_valid_d;

    always_ff @(posedge clk) begin

        if (!rst_n) begin
            cfg_valid_d  <= 1'b0;

            counter0     <= 8'd0;
            counter1     <= 8'd0;

            counter0_tick <= 1'b0;
            counter1_tick <= 1'b0;

            shift0 <= 8'd0;
            shift1 <= 8'd0;

        end else begin

            cfg_valid_d <= cfg_valid;

            if (!cfg_valid) begin

                counter0 <= 8'd0;
                counter1 <= 8'd0;

                counter0_tick <= 1'b0;
                counter1_tick <= 1'b0;

                shift0 <= 8'd0;
                shift1 <= 8'd0;

            end

            // Initialize programmable resources once
            // a complete configuration is accepted.
            else if (!cfg_valid_d) begin

                counter0 <= 8'd0;
                counter1 <= 8'd0;

                counter0_tick <= 1'b0;
                counter1_tick <= 1'b0;

                shift0 <= cfg[173:166];
                shift1 <= cfg[188:181];

            end

            else begin

                // Counter 0
                counter0_tick <= 1'b0;

                if (cfg[156]) begin
                    if ((cfg[155:148] == 8'd0) ||
                        (counter0 >= cfg[155:148] - 8'd1)) begin

                        counter0 <= 8'd0;
                        counter0_tick <= 1'b1;

                    end else begin
                        counter0 <= counter0 + 8'd1;
                    end
                end else begin
                    counter0 <= 8'd0;
                end

                // Counter 1
                counter1_tick <= 1'b0;

                if (cfg[165]) begin
                    if ((cfg[164:157] == 8'd0) ||
                        (counter1 >= cfg[164:157] - 8'd1)) begin

                        counter1 <= 8'd0;
                        counter1_tick <= 1'b1;

                    end else begin
                        counter1 <= counter1 + 8'd1;
                    end
                end else begin
                    counter1 <= 8'd0;
                end

                // Shift register 0
                if (cfg[179]) begin
                    if (cfg[180])
                        shift0 <= {
                            route_select(
                                cfg[178:174], io_in, lut_q,
                                counter0[7], counter1[7],
                                counter0_tick, counter1_tick,
                                shift0[7], shift1[7],
                                shift0[0], shift1[0],
                                pwm0, pwm1
                            ),
                            shift0[7:1]
                        };
                    else
                        shift0 <= {
                            shift0[6:0],
                            route_select(
                                cfg[178:174], io_in, lut_q,
                                counter0[7], counter1[7],
                                counter0_tick, counter1_tick,
                                shift0[7], shift1[7],
                                shift0[0], shift1[0],
                                pwm0, pwm1
                            )
                        };
                end

                // Shift register 1
                if (cfg[194]) begin
                    if (cfg[195])
                        shift1 <= {
                            route_select(
                                cfg[193:189], io_in, lut_q,
                                counter0[7], counter1[7],
                                counter0_tick, counter1_tick,
                                shift0[7], shift1[7],
                                shift0[0], shift1[0],
                                pwm0, pwm1
                            ),
                            shift1[7:1]
                        };
                    else
                        shift1 <= {
                            shift1[6:0],
                            route_select(
                                cfg[193:189], io_in, lut_q,
                                counter0[7], counter1[7],
                                counter0_tick, counter1_tick,
                                shift0[7], shift1[7],
                                shift0[0], shift1[0],
                                pwm0, pwm1
                            )
                        };
                end

            end
        end
    end

    // =========================================================
    // FOUR LUT4 BLOCKS
    // =========================================================

    genvar i;
    genvar j;

    generate
        for (i = 0; i < 4; i = i + 1) begin : g_lut

            wire [3:0] sel_in;
            wire [15:0] table_bits;

            assign table_bits = cfg[i*16 +: 16];

            for (j = 0; j < 4; j = j + 1) begin : g_input

                assign sel_in[j] = route_select(
                    cfg[64 + (i*4+j)*5 +: 5],
                    io_in,
                    lut_q,
                    counter0[7],
                    counter1[7],
                    counter0_tick,
                    counter1_tick,
                    shift0[7],
                    shift1[7],
                    shift0[0],
                    shift1[0],
                    pwm0,
                    pwm1
                );

            end

            assign lut_result[i] = table_bits[sel_in];

        end
    endgenerate

    // =========================================================
    // LUT OUTPUT REGISTERS
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
