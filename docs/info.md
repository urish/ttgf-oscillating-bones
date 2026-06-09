<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

A stylish ring oscillator built from **SkullFET** transistors — MOSFETs hand-drawn in the shape
of skulls. A chain of 21 SkullFET inverters forms a ring oscillator that generates a square wave,
and a frequency divider produces /2, /4 and /8 taps.

This is the **gf180mcu** (GlobalFoundries 180nm) port of the design, migrated from the original
IHP sg13g2 version. The SkullFETs are **3.3V devices** running directly on the 3.3V core supply
(VDPWR). The skull artwork is preserved verbatim from the original; only the layer stack, device
implants and feature sizes were retargeted to gf180mcuD (a uniform 1.45× scale clears the 180nm
minimum width/spacing/gate rules — see `scripts/remap_to_gf180.py`).

![Layout](layout.png)

| Pin       | Signal      | Post-layout frequency |
|-----------|-------------|-----------------------|
| ua[0]     | osc_out_3v3 (raw 3.3V oscillation) | ~119 MHz |
| uo_out[0] | osc_out     | ~119 MHz |
| uo_out[1] | osc_div_2   | ~59 MHz  |
| uo_out[2] | osc_div_4   | ~30 MHz  |
| uo_out[3] | osc_div_8   | ~15 MHz  |

**Post-layout simulation** (extract the hardened GDS with magic, simulate with the gf180mcuD
ngspice models — run `make sim`): the ring oscillates **rail-to-rail at ~119 MHz**, and the
std-cell ripple divider produces clean **/2, /4, /8** taps on `uo_out[1..3]`. The raw 3.3V
oscillation is also on the analog pin `ua[0]`. The testbench supplies only VDPWR/VGND and the
substrate bias — it does **not** force any std-cell rail or device well, so the result reflects the
actual extracted connectivity (every pfet body is tied to VDPWR through its n-well tap, every
std-cell rail is strapped to VDPWR/VGND — nothing floats).

## Reset

`rst_n` (active-low) resets **only the divider** — it asynchronously clears the three flip-flops,
so while `rst_n` is held low the divided taps `uo_out[1..3]` (÷2/÷4/÷8) sit at 0. The 21-stage ring
oscillator has no reset and free-runs whenever the design is powered, so `osc_out` / `ua[0]` keep
oscillating at full speed even during reset. Release `rst_n` (high) and the divider starts counting
from a known phase. `clk` and `ena` are not used — the ring self-clocks the divider.

## How to test

Connect an oscilloscope to **`osc_div_8` / `uo_out[3]`** (~15 MHz, scope-friendly) and enjoy the
show. The faster taps (`osc_out`, `osc_div_2`) exceed typical GPIO bandwidth — observe the raw
oscillation on the analog pin **`ua[0]`** instead. Note that `uo_out[1..3]` stay at 0 until you
release `rst_n`.

## External hardware

None — just an oscilloscope.
