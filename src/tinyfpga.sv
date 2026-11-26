v
`default_nettype none

module tinyfpga (
    input  logic       clk,
    input  logic       rst_n,

    // SPI configuration interface (Mode 0, MSB first)
    input  logic       spi_sclk,
    input  logic       spi_cs_n,
    input  logic       spi_mosi,
    output logic       spi_miso,

    // FPGA fabric I/O
    input  logic [7:0] io_in,
    output logic [3:0] io_out
);

    // Configuration:
    // [63:0]   Four 16-bit LUT truth tables
    // [127:64] Sixteen 4-bit routing selectors
    // [131:128] Four output register-mode bits

    localparam CFG_BITS = 132;

    // ---------------------------------------------------------
    // SPI synchronization
    // ---------------------------------------------------------

    logic [2:0] sclk_s;
    logic [2:0] cs_s;
    logic [1:0] mosi_s;

    logic sclk_rise;
    logic cs_active;
    logic cs_rise;

    assign sclk_rise = (sclk_s[2:1] == 2'b01);
    assign cs_active = ~cs_s[1];
    assign cs_rise   = (cs_s[2:1] == 2'b01);

    // ---------------------------------------------------------
    // SPI configuration receiver
    // ---------------------------------------------------------

    logic [CFG_BITS-1:0] spi_rx_shift;
    logic [CFG_BITS-1:0] cfg;

    logic [7:0] bit_cnt;

    // Shift incoming configuration data.
    // Configuration is committed only after exactly 132 bits.

    always_ff @(posedge clk) begin
        if (rst_n && cs_active && sclk_rise) begin
            spi_rx_shift <= {
                spi_rx_shift[CFG_BITS-2:0],
                mosi_s[1]
            };
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            sclk_s  <= 3'b000;
            cs_s    <= 3'b111;
            mosi_s  <= 2'b00;

            bit_cnt <= 8'd0;
            cfg     <= {CFG_BITS{1'b0}};
        end else begin

            // Synchronize SPI inputs
            sclk_s <= {sclk_s[1:0], spi_sclk};
            cs_s   <= {cs_s[1:0], spi_cs_n};
            mosi_s <= {mosi_s[0], spi_mosi};

            // Count received SPI bits
            if (!cs_active) begin
                bit_cnt <= 8'd0;
            end
            else if (sclk_rise && bit_cnt < 8'd132) begin
                bit_cnt <= bit_cnt + 8'd1;
            end

            // Commit configuration after exactly 132 bits
            if (cs_rise && bit_cnt == 8'd132) begin
                cfg <= spi_rx_shift;
            end
        end
    end

    // Write-only SPI interface
    assign spi_miso = 1'b0;

    // ---------------------------------------------------------
    // Configuration decode
    // ---------------------------------------------------------

    logic [3:0] reg_mode;

    assign reg_mode = cfg[131:128];

    // ---------------------------------------------------------
    // Routing selector
    // ---------------------------------------------------------

    function automatic logic route_select (
        input logic [3:0] select,
        input logic [7:0] external_inputs,
        input logic [3:0] internal_outputs
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

                4'd8:  route_select = internal_outputs[0];
                4'd9:  route_select = internal_outputs[1];
                4'd10: route_select = internal_outputs[2];
                4'd11: route_select = internal_outputs[3];

                4'd13: route_select = 1'b1;

                default: route_select = 1'b0;
            endcase
        end

    endfunction

    // ---------------------------------------------------------
    // Four configurable LUT4 blocks
    // ---------------------------------------------------------

    logic [3:0] lut_q;
    logic [3:0] lut_result;

    genvar i;
    genvar j;

    generate
        for (i = 0; i < 4; i = i + 1) begin : g_lut

            wire [3:0] sel_in;
            wire [15:0] table_bits;

            assign table_bits = cfg[i*16 +: 16];

            for (j = 0; j < 4; j = j + 1) begin : g_in

                assign sel_in[j] = route_select(
                    cfg[64 + (i*4 + j)*4 +: 4],
                    io_in,
                    lut_q
                );

            end

            // LUT truth-table lookup
            assign lut_result[i] = table_bits[sel_in];

        end
    endgenerate

    // ---------------------------------------------------------
    // Optional output registers
    // ---------------------------------------------------------

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            lut_q <= 4'b0000;
        end else begin
            lut_q <= lut_result;
        end
    end

    // Select registered or combinational LUT output
    assign io_out = (reg_mode & lut_q) |
                    ((~reg_mode) & lut_result);

endmodule

`default_nettype wire
