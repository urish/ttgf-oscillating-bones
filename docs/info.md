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
| ua[0]     | osc_out_3v3 (raw 3.3V oscillation) |
| uo_out[0] | osc_out     |
| uo_out[1] | osc_div_2   |
| uo_out[2] | osc_div_4   |
| uo_out[3] | osc_div_8   |

**Post-layout simulation:** the ring oscillates **rail-to-rail at ~122 MHz** on gf180mcu
(vs ~150 MHz on IHP — slightly lower as expected for the 180nm node and 1.45× geometry). The raw
oscillation is brought out on the analog pin **`ua[0]` (osc_out_3v3)**, verified by extracting the
hardened GDS with magic and simulating with the gf180mcuD ngspice models.

> The digital outputs `uo_out[0..3]` (osc_out + /2 /4 /8 divider) still need their pin routing and
> the gf180 std-cell divider — see [`MIGRATION.md`](../MIGRATION.md). The working output today is
> `ua[0]`.

## How to test

Connect an oscilloscope to the analog pin **`ua[0]`** to see the raw ~122 MHz oscillation. (Note
that 122 MHz exceeds typical GPIO bandwidth, so the analog pin is the best observation point.)

## External hardware

None — just an oscilloscope.
