# AGENTS.md

Operational guide for working on **Oscillating Bones** — a gf180mcuD analog Tiny Tapeout project.
For *why* the layout is the way it is (device recipe, gotchas, design rationale), see
[`DESIGN.md`](DESIGN.md).

## What this is

A hand-drawn **custom-GDS** analog macro: a 21-stage SkullFET ring oscillator (~120 MHz) → a
SkullFET inverter buffering the raw oscillation onto `ua[0]` (`osc_out`), plus an 8-bit std-cell
ripple divider on `uo_out[0..7]` (= /2 .. /256, LSB-first). The real circuit is the **committed
GDS**, assembled by Python; `src/project.v` is only the black-box pin interface.

## Build & verify

```
make all      # assemble gds/ + lef/ from gds/ring_gf180.gds (the committed artwork)
make drc      # magic sign-off DRC — must report 0
make sim      # post-layout ngspice: ring frequency + /2../256 divider
make plot     # regenerate docs/layout_sim.png (waveforms)
make lvs      # netgen device/net cross-check
```

The authoritative gate (also run in CI) is the Tiny Tapeout precheck:
`tt-support-tools/precheck/precheck.py` structural checks (boundary / layer / power-pin / analog-pin
/ pin) + the KLayout DRC decks. **After any layout change, re-run `make drc` (must be 0), `make sim`,
and the precheck**, and confirm nothing floats (see rules below).

## Toolchain (this environment)

- **No system `magic` / `netgen` / `klayout` binary.** `magic` and `netgen` run via `nix-portable`
  wrappers at `~/bin/magic` / `~/bin/netgen` (realized from the fossi cache). `klayout` is the
  **python module** only (`pya`); the KLayout-DSL DRC decks need the binary and run in CI.
- **PDK**: gf180mcuD installed via ciel — set `PDK_ROOT` to the ciel `.../versions/<hash>` dir and
  `PDK=gf180mcuD` (the magicrc, ngspice models and DRC decks live under there).
- Also available: `gdstk`, `ngspice`, `numpy`, `matplotlib`, `librelane`.

## Repo map / build flow

- `gds/ring_gf180.gds` — **the committed source artwork** (the remapped gf180 skull ring); the build
  starts here. The IHP source was removed post-migration; `make remap IHP_SRC=<ihp.gds>` regenerates
  it via `scripts/remap_to_gf180.py`.
- `gds/skull_buffer.gds` — the committed single-skull buffer cell (one remapped inverter).
- `scripts/build_gf180_macro.py` — assembles the macro: DEF frame + Metal4 pins + left-edge power
  stripes + placed ring + `add_ua_buffer` (ua[0] buffer) + `add_divider` (8-bit divider); emits the LEF.
- `scripts/build_divider.py` — the std-cell divider row (`dffrnq_1` + `inv_2` toggle stages, with
  `filltie`/`endcap` for the well taps).
- helpers: `scripts/{remap_to_gf180,render_layout,plot_wave,gen_lvs_source}.py`,
  `scripts/{sim_ring,sim_plot,run_lvs}.sh`, `scripts/extract_{sim,lvs}.tcl`.

## Rules you must not break

- **Never force-tie power/wells in simulation.** `scripts/sim_ring.sh` ties only the global
  substrate; std-cell rails and device wells are used **as extracted**, so a missing power route
  breaks the sim instead of being masked. (A force-tie once hid a disconnected divider VDD rail and
  floating n-wells.) After a layout change, the raw extraction must contain **no** `.VDD/.VSS/.VNW/
  .VPW` or floating `w_*` well nets.
- **Routing discipline** (`add_divider`, `add_ua_buffer`): Metal3 = horizontal tracks (unique y per
  net), Metal4 = vertical risers (unique x). Different-net M3×M4 crossings can't short — keep it so.
  The divider is horizontally mirrored so the ÷2..÷256 stages line up with the pin order: the eight
  output taps fan straight down without crossing, and the clock rises up the free **right** edge from
  the buffered `ua[0]` node (no left-edge detour, no Metal3 dip).
- **Implant polarity follows the original p-select (pSD), not Nwell membership** (`regen_implants`
  in `remap_to_gf180.py`): keying off Nwell buries the n+ n-well taps and floats the pfet bodies.
- **Both power stripes sit on the LEFT edge** (VGND leftmost, VDPWR just inside), spanning ~97 % of
  die height (analog power pins must span > 90 %).
- `gds/ring_gf180.gds` and `gds/skull_buffer.gds` are **committed build inputs** — `make clean` must
  not delete them.
- Keep the pin tables in `docs/info.md`, `info.yaml` and `src/project.v` in sync: `ua[0]=osc_out`;
  `uo_out[0..7] = osc_div_2 .. osc_div_256` (LSB-first).
