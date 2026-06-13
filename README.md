![](../../workflows/gds/badge.svg) ![](../../workflows/docs/badge.svg)

# Oscillating Bones for Tiny Tapeout (gf180mcu)

A stylish ring oscillator built from skull-shaped **SkullFET** transistors — the **gf180mcu**
(GlobalFoundries 180nm) port of the design, for the ttgf0p3 experimental shuttle.

- [Read the documentation for project](docs/info.md)

## Building the layout

The gf180 skull ring (`gds/ring_gf180.gds`) is committed as the source artwork; the full macro is
assembled from it by a pure-Python pipeline (no interactive layout needed):

```
make all      # assemble the macro (GDS + LEF) from gds/ring_gf180.gds
make drc      # magic sign-off DRC (0 violations)
make sim      # post-layout ngspice: ring + 8-bit /2../256 divider
make lvs      # netgen device/net cross-check
```

- `scripts/build_gf180_macro.py` — assembles the full `tt_um_oscillating_bones` macro from the
  TT analog DEF frame (pins + power stripes) with the skull ring placed in the centre and a gf180
  std-cell 8-bit /2../256 divider (`scripts/build_divider.py`), and emits the matching LEF.
- `scripts/render_layout.py` — renders the GDS to a PNG.
- `scripts/remap_to_gf180.py` — the one-time IHP sg13g2 → gf180mcuD migration that produced
  `ring_gf180.gds` (3.3V devices, implants/n-well taps regenerated from the original p-select,
  1.45× scale). The IHP source GDS has been removed post-migration; to re-run it against a fresh
  IHP source: `make remap IHP_SRC=path/to/ihp_source.gds`.

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
