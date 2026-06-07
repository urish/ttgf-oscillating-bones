![](../../workflows/gds/badge.svg) ![](../../workflows/docs/badge.svg)

# Oscillating Bones for Tiny Tapeout (gf180mcu)

A stylish ring oscillator built from skull-shaped **SkullFET** transistors — the **gf180mcu**
(GlobalFoundries 180nm) port of the design, for the ttgf0p3 experimental shuttle.

- [Read the documentation for project](docs/info.md)

## Building the layout

The hand-drawn SkullFET artwork is migrated from IHP sg13g2 to gf180mcuD by a pure-Python
pipeline (no interactive layout needed):

```
make all      # remap the skull ring to gf180 layers + assemble the macro (GDS + LEF)
make drc      # magic sign-off DRC (0 violations)
```

- `scripts/remap_to_gf180.py` — remaps the IHP SkullFET ring to gf180mcuD layers, regenerates
  the well/implant layers as 3.3V devices (no Dualgate), and scales 1.45× to clear 180nm rules.
- `scripts/build_gf180_macro.py` — assembles the full `tt_um_oscillating_bones` macro from the
  TT analog DEF frame (pins + power stripes) with the skull ring placed in the centre, and emits
  the matching LEF.
- `scripts/render_layout.py` — renders the GDS to a PNG.

Requires `PDK_ROOT` pointing at a gf180mcuD install and `magic` on `PATH`.

See [`MIGRATION.md`](MIGRATION.md) for the full migration notes, what is validated, and the
remaining functional finalisation steps.

## What is Tiny Tapeout?

Tiny Tapeout is an educational project that aims to make it easier and cheaper than ever to get your digital designs manufactured on a real chip.

To learn more and get started, visit https://tinytapeout.com.

## Analog projects

For specifications and instructions, see the [analog specs page](https://tinytapeout.com/specs/analog/).

## Resources

- [FAQ](https://tinytapeout.com/faq/)
- [Digital design lessons](https://tinytapeout.com/digital_design/)
- [Learn how semiconductors work](https://tinytapeout.com/siliwiz/)
- [Join the community](https://tinytapeout.com/discord)
