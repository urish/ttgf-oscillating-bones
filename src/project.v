/*
 * Copyright (c) 2024-2026 Uri Shaked
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

// Oscillating Bones - a ring oscillator built from skull-shaped SkullFET transistors.
// This is an *analog* project: the real circuit lives in the hand-drawn custom GDS
// (gds/tt_um_oscillating_bones.gds). This Verilog is only the black-box interface that
// the Tiny Tapeout harness wires up.
module tt_um_oscillating_bones (
    input  wire       VGND,
    input  wire       VDPWR,    // 3.3V core power supply (the ring runs on this)
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs (8-bit divider, osc_div_2 .. osc_div_256)
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    inout  wire [7:0] ua,       // Analog pins; ua[0] = osc_out (buffered raw 3.3V oscillation)
    input  wire       ena,      // always 1 when the design is powered
    input  wire       clk,      // clock (unused)
    input  wire       rst_n     // reset_n - low to reset the frequency divider
);

  // Outputs driven by the analog macro (8-bit ripple divider, LSB first):
  //   uo_out[0] = osc_div_2      uo_out[4] = osc_div_32
  //   uo_out[1] = osc_div_4      uo_out[5] = osc_div_64
  //   uo_out[2] = osc_div_8      uo_out[6] = osc_div_128
  //   uo_out[3] = osc_div_16     uo_out[7] = osc_div_256
  //   ua[0]     = osc_out       (buffered raw ~120 MHz oscillation)
  // All unused outputs are tied low in the macro: uio_out[7:0] = 0 and uio_oe[7:0] = 0
  // (so the bidirectional pads stay in input / high-Z mode).

endmodule
`default_nettype wire
