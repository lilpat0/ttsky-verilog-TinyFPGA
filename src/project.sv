
`default_nettype none

module tt_um_tinyfpga (
    input  logic [7:0] ui_in,
    output logic [7:0] uo_out,

    input  logic [7:0] uio_in,
    output logic [7:0] uio_out,
    output logic [7:0] uio_oe,

    input  logic       ena,
    input  logic       clk,
    input  logic       rst_n
);

    // ---------------------------------------------------------
    // Internal signals
    // ---------------------------------------------------------

    logic       spi_miso;
    logic [3:0] fabric_out;

    // ---------------------------------------------------------
    // TinyFPGA core
    // ---------------------------------------------------------

    tinyfpga u_core (
        .clk      (clk),
        .rst_n    (rst_n),

        // SPI configuration interface
        .spi_sclk (uio_in[0]),
        .spi_cs_n (uio_in[1]),
        .spi_mosi (uio_in[2]),
        .spi_miso (spi_miso),

        // FPGA fabric interface
        .io_in    (ui_in),
        .io_out   (fabric_out)
    );

    // ---------------------------------------------------------
    // Dedicated outputs
    // ---------------------------------------------------------

    assign uo_out = {
        4'b0000,
        fabric_out
    };

    // ---------------------------------------------------------
    // SPI MISO output
    // ---------------------------------------------------------

    assign uio_out = {
        4'b0000,
        spi_miso,
        3'b000
    };

    // Only UIO[3] is an output.
    // UIO[0], UIO[1], UIO[2] remain inputs.

    assign uio_oe = 8'b0000_1000;

    // ---------------------------------------------------------
    // Unused signals
    // ---------------------------------------------------------

    wire unused = &{ena, uio_in[7:3], 1'b0};

endmodule

`default_nettype wire
