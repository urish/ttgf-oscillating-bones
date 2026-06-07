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

| Pin       | Signal      |
|-----------|-------------|
| uo_out[0] | osc_out     |
| uo_out[1] | osc_div_2   |
| uo_out[2] | osc_div_4   |
| uo_out[3] | osc_div_8   |
| ua[0]     | osc_out_3v3 (raw 3.3V oscillation) |

> **Note:** the oscillation frequency on gf180mcu differs from the IHP version and must be
> re-characterised in simulation. The 180nm devices and 1.45× geometry give a lower frequency
> than the original ~150 MHz; the divided taps (`osc_div_8` / `uo_out[3]`) are the easiest to
> observe on a scope.

## How to test

Connect an oscilloscope to one of the output pins (e.g. `osc_div_8` / `uo_out[3]`) and enjoy the
show. The raw 3.3V oscillation is also available on the analog pin `ua[0]`.

## External hardware

None — just an oscilloscope.
