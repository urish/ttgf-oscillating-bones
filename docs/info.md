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
| ua[0]     | osc_out_3v3 (raw 3.3V oscillation) | ~139 MHz |
| uo_out[0] | osc_out     | ~139 MHz |
| uo_out[1] | osc_div_2   | ~70 MHz  |
| uo_out[2] | osc_div_4   | ~35 MHz  |
| uo_out[3] | osc_div_8   | ~17 MHz  |

**Post-layout simulation** (extract the hardened GDS with magic, simulate with the gf180mcuD
ngspice models — run `make sim`): the ring oscillates **rail-to-rail at ~139 MHz**, and the
std-cell ripple divider produces clean **/2, /4, /8** taps on `uo_out[1..3]`. The raw 3.3V
oscillation is also on the analog pin `ua[0]`. The testbench supplies only VDPWR/VGND and the
substrate bias — it does not force any std-cell rail or device well, so the result reflects the
actual extracted connectivity.

## How to test

Connect an oscilloscope to **`osc_div_8` / `uo_out[3]`** (~17 MHz, scope-friendly) and enjoy the
show. The faster taps (`osc_out`, `osc_div_2`) exceed typical GPIO bandwidth — observe the raw
oscillation on the analog pin **`ua[0]`** instead.

## External hardware

None — just an oscilloscope.
