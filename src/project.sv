// project.sv
// Tiny Tapeout wrapper. Pin mapping only; all logic lives in tinyfpga.sv.
//
//   ui_in[7:0]   -> fabric inputs io_in[7:0]
//   uo_out[3:0]  <- fabric outputs io_out[3:0], uo_out[7:4] tied low
//   uio[0] in    SPI SCLK
//   uio[1] in    SPI CS_n
//   uio[2] in    SPI MOSI
//   uio[3] out   SPI MISO (always 0, write-only interface)

`default_nettype none

module tt_um_tinyfpga (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: input path
    output wire [7:0] uio_out,  // IOs: output path
    output wire [7:0] uio_oe,   // IOs: enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered
    input  wire       clk,
    input  wire       rst_n
);

    logic       spi_miso;
    logic [3:0] fabric_out;

    tinyfpga u_core (
        .clk      (clk),
        .rst_n    (rst_n),
        .spi_sclk (uio_in[0]),
        .spi_cs_n (uio_in[1]),
        .spi_mosi (uio_in[2]),
        .spi_miso (spi_miso),
        .io_in    (ui_in),
        .io_out   (fabric_out)
    );

    assign uo_out  = {4'b0000, fabric_out};
    assign uio_out = {4'b0000, spi_miso, 3'b000};
    assign uio_oe  = 8'b0000_1000;

    // Unused inputs
    wire _unused = &{ena, uio_in[7:3], 1'b0};

endmodule

`default_nettype wire
