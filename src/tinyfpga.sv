// tinyfpga.sv
// Logic core: 4x LUT4 + full input crossbar + optional output registers,
// configured over SPI (Mode 0, MSB first, exactly 132 bits per transaction).
// No Tiny Tapeout specifics here; see project.sv for the pin wrapper.
//
// Everything runs on clk. The SPI pins are synchronized, so clk must be
// at least ~4x faster than spi_sclk.
//
// Config bit layout (bit 131 is sent first, bit 0 last):
//   [ 63:  0]  4 x 16-bit LUT truth tables (LUT i = bits [i*16 +: 16])
//   [127: 64]  16 x 4-bit route selects (LUT i input j = bits [64 + (i*4+j)*4 +: 4])
//   [131:128]  reg_mode (1 = output i comes from the register)
//
// Route select values:
//   0-7  io_in[0..7]     8-11 registered LUT outputs 0..3
//   12   const 0         13   const 1       14,15 const 0

`default_nettype none

module tinyfpga (
    input  logic       clk,
    input  logic       rst_n,

    // SPI configuration interface (write-only)
    input  logic       spi_sclk,
    input  logic       spi_cs_n,
    input  logic       spi_mosi,
    output logic       spi_miso,

    // Fabric I/O
    input  logic [7:0] io_in,
    output logic [3:0] io_out
);

    localparam int CFG_BITS = 132;

    // ---------------------------------------------------------
    // SPI front end (all in the clk domain)
    // ---------------------------------------------------------
    logic [2:0] sclk_s, cs_s;
    logic [1:0] mosi_s;

    logic [CFG_BITS-1:0] spi_rx_shift;   // no reset: overwritten each transaction
    logic [CFG_BITS-1:0] cfg;
    logic [7:0]          bit_cnt;        // saturating count of SCLK rising edges

    logic sclk_rise, cs_active, cs_rise;

    assign sclk_rise = (sclk_s[2:1] == 2'b01);
    assign cs_active = ~cs_s[1];
    assign cs_rise   = (cs_s[2:1] == 2'b01);

    always_ff @(posedge clk) begin
        if (cs_active && sclk_rise)
            spi_rx_shift <= {spi_rx_shift[CFG_BITS-2:0], mosi_s[1]};
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            sclk_s  <= 3'b000;
            cs_s    <= 3'b111;
            mosi_s  <= 2'b00;
            bit_cnt <= 8'd0;
            cfg     <= '0;
        end else begin
            sclk_s <= {sclk_s[1:0], spi_sclk};
            cs_s   <= {cs_s[1:0],   spi_cs_n};
            mosi_s <= {mosi_s[0],   spi_mosi};

            // Count clocks while selected; clear while deselected
            if (!cs_active)
                bit_cnt <= 8'd0;
            else if (sclk_rise && bit_cnt != 8'hFF)
                bit_cnt <= bit_cnt + 8'd1;

            // Commit only if exactly 132 bits were received
            if (cs_rise && bit_cnt == 8'(CFG_BITS))
                cfg <= spi_rx_shift;
        end
    end

    assign spi_miso = 1'b0;

    // ---------------------------------------------------------
    // Config decode
    // ---------------------------------------------------------
    logic [3:0] reg_mode;
    assign reg_mode = cfg[131:128];

    // ---------------------------------------------------------
    // Routing matrix
    // ---------------------------------------------------------
    function automatic logic route_select (
        input logic [3:0] select,
        input logic [7:0] external_inputs,
        input logic [3:0] internal_outputs
    );
        case (select)
            4'd0:    return external_inputs[0];
            4'd1:    return external_inputs[1];
            4'd2:    return external_inputs[2];
            4'd3:    return external_inputs[3];
            4'd4:    return external_inputs[4];
            4'd5:    return external_inputs[5];
            4'd6:    return external_inputs[6];
            4'd7:    return external_inputs[7];
            4'd8:    return internal_outputs[0];
            4'd9:    return internal_outputs[1];
            4'd10:   return internal_outputs[2];
            4'd11:   return internal_outputs[3];
            4'd13:   return 1'b1;
            default: return 1'b0;      // 12, 14, 15
        endcase
    endfunction

    // ---------------------------------------------------------
    // LUT array
    // ---------------------------------------------------------
    logic [3:0] lut_q;
    logic [3:0] lut_result;

    genvar i, j;
    generate
        for (i = 0; i < 4; i++) begin : g_lut
            logic [3:0]  sel_in;
            logic [15:0] table_bits;

            assign table_bits = cfg[i*16 +: 16];

            for (j = 0; j < 4; j++) begin : g_in
                assign sel_in[j] = route_select(cfg[64 + (i*4 + j)*4 +: 4],
                                                io_in, lut_q);
            end

            assign lut_result[i] = table_bits[sel_in];
        end
    endgenerate

    // ---------------------------------------------------------
    // Output registers and output select
    // ---------------------------------------------------------
    always_ff @(posedge clk) begin
        if (!rst_n)
            lut_q <= 4'b0000;
        else
            lut_q <= lut_result;
    end

    assign io_out = (reg_mode & lut_q) | (~reg_mode & lut_result);

endmodule

`default_nettype wire
