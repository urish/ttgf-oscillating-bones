# Design notes

How **Oscillating Bones** is built on **gf180mcuD** (for the **ttgf0p3** shuttle), and *why* the
layout is the way it is — the device recipe, the connectivity gotchas we hit, and the divider /
buffer / power / LVS rationale. For how to build, simulate and verify the repo, see
[`AGENTS.md`](AGENTS.md).

The design is a hand-drawn analog macro (a ring of skull-shaped SkullFET transistors) ported at the
**layout level** from the original IHP sg13g2 version, using the
[ttgf-analog-template](https://github.com/TinyTapeout/ttgf-analog-template) conventions and the
`tt-support-tools/tech/gf180mcuD/def/analog` frame. The skull artwork is preserved verbatim; the
layer stack, device implants and feature sizes are retargeted to gf180mcuD in a pure-Python
pipeline.

### The SkullFET device recipe (`scripts/remap_to_gf180.py`)

- **Layer remap** (IHP → gf180mcuD): Activ→COMP (22/0), GatPoly→Poly2 (30/0), Cont→Contact (33/0),
  Metal1-4 → 34/36/42/46, Via1/2/3/4 → 35/38/40/41, NWell→Nwell (21/0). The IHP 7-metal stack
  collapses to gf180's 4 usable routing metals (Metal5/81 is forbidden, MetalTop unreachable):
  M5/TopMetal1/TopMetal2 fold onto Metal4.
- **3.3V devices — no Dualgate.** This is the key insight. Marking Dualgate(55/0) makes magic
  extract the FETs as **6V medium-voltage** devices (gate ≥ 0.55/0.70 µm), which would force a
  ~2.5× blow-up that no longer fits the die. As plain **3.3V devices** (nfet_03v3/pfet_03v3, no
  Dualgate) the gate minimum is 0.28 µm — matching the 3.3V core supply.
- **Implant regeneration follows the original p-select (pSD), not Nwell membership**: Pplus =
  COMP ∩ pSD (+0.16 µm), Nplus = COMP − pSD (+0.16 µm), LVPWELL over the NMOS (n+ COMP *outside*
  the Nwell); Nwell grown +0.30 µm for DF.7. This polarity choice matters: the bare n+ COMP inside
  each Nwell are the **n-well taps** that tie the pfet bodies to VDPWR. An earlier version keyed
  the implants off Nwell membership (p+ for all COMP in the Nwell), which buried those taps under
  Pplus and left all 21 pfet bodies floating — the design still oscillated (junction-biased), but
  the bodies weren't tied. Honoring pSD restores the taps (every pfet body extracts to VDPWR).
- **1.45× uniform scale** — the minimum that clears every 180nm width/spacing/cut rule.

Result: the full skull ring (21 inverters + central skull + power rings) remaps to a
**261 × 261 µm, 0-DRC-violation** block.

### Macro assembly (`scripts/build_gf180_macro.py`)

Builds `tt_um_oscillating_bones` (346.64 × 325.36 µm, 1×2 tile) from the TT analog DEF: all 51
Metal4 signal pins at the template positions, VGND/VDPWR Metal4 power stripes, the PR_bndry (0/0)
die outline, and the skull ring placed in the centre. Emits the matching LEF (correct SIZE,
`DIRECTION`, `USE POWER`/`USE GROUND`).

All **unused output pins are tied low** (`tie_unused_low`): `uio_out[7:0]` and the output-enables
`uio_oe[7:0]` sit contiguously on the top edge, so a Metal4 rail just below the pin row taps all 16
and grounds them to the VGND stripe (the macro drives a clean 0 on every unused output, and the
low output-enables keep the bidirectional pads in input/high-Z mode).

## What is validated ✅

- **Full KLayout sign-off DRC: 0 real violations** (`make drc_klayout` — the authoritative
  gf180mcuD `gf180mcu.drc` deck, FEOL + BEOL + connectivity + antenna, deep mode). The only hits
  are the seven **die-level density** rules (PL.8 poly, M1–M5.4 / MT.3 metal coverage) that are
  satisfied by dummy fill at chip integration, not by an individual macro — the taped-out reference
  projects on this shuttle carry the identical seven. **Magic DRC also reports 0**, but note it is a
  *weaker* check: it does not verify the 5 nm manufacturing grid, the exact contact/via sizes, or
  metal slotting, so the KLayout deck is the gate that matters. Getting there required, beyond the
  base remap: snapping all geometry to the 5 nm grid, rebuilding every cut at its exact gf180 size
  (Contact 0.22 / Via 0.26), merging same-type implants (NP.2/PP.2) and clipping them off the
  opposite diffusion (PP.3a), and slotting the skull's wide solid metal (MSLOT.1) — see
  `remap_to_gf180.py` / `scripts/sanitize_gf180.py`.
- **Post-layout SPICE oscillates and divides.** Extracting the hardened GDS with magic and
  simulating with the gf180mcuD ngspice models (`make sim`), the 21-stage ring oscillates
  **rail-to-rail at ~120 MHz**, and the 8-bit std-cell ripple divider produces clean **/2 .. /256**
  taps: `uo_out[0]=÷2` ~60 MHz up to `uo_out[7]=÷256` ~0.47 MHz; the buffered raw oscillation is
  on `ua[0]`. The testbench supplies **only VDPWR/VGND and the substrate bias** — it does **not**
  force any std-cell rail or device well, so the behaviour reflects the *actual* extracted
  connectivity: every pfet body ties to VDPWR through its n-well tap, every std-cell rail is
  strapped to VDPWR/VGND, and the extraction shows **no floating well/rail nets**.
- **TT precheck structural checks pass** (run locally against `tt-support-tools/precheck`):
  KLayout Checks, Boundary check, Layer check, Cell name check, Power pin check, Analog pin check,
  Pin check.
- **Verilog syntax check** passes (yosys).
- Config migrated: `info.yaml`, workflows (`@ttgf26a`, `pdk: gf180mcuD`), `src/project.v`, `Makefile`.

Two key fixes were needed to get the post-layout netlist to oscillate: (a) the inverter cells
carried decorative power-ring stubs on the upper metals that, after the 7→4 metal collapse, shorted
each inverter's VGND to VDPWR — these are dropped in the remap; (b) the per-inverter A/Y pin labels
must NOT be carried into the flattened ring (they would merge all inputs/outputs); inter-stage
connectivity is geometric. Both power stripes sit on the **left** die edge (VGND leftmost, VDPWR
just inside it), matching the original IHP arrangement so the TT power grid — which enters from the
left — connects without strips reaching across the skull. They run ~97% of the die height. The two
supply connectors land on left-side ring pads at well-separated angles (different y); the VGND
connector hops the VDPWR stripe on a short Metal3 dip (outside the ring, clear of the Metal3 rings).
With the divider mirrored, the clock riser now climbs the free **right** edge to the CLK pin and
never touches the left-side connectors. Verified after the move: VGND and VDPWR remain separate
nets, every ring pfet body + std-cell rail stays tied, nothing floats.

The KLayout FEOL/BEOL/offgrid/antenna decks need the KLayout binary (not the Python module) and run
in CI; magic DRC runs clean locally.

## The 8-bit /2../256 divider (`scripts/build_divider.py`)

The divider is an **8-stage** ripple counter of `gf180mcu_fd_sc_mcu7t5v0` std cells: each /2 stage
is a **`dffrnq_1`** DFF + an **`inv_2`** wired as a toggle FF (D = ~Q, since gf180 DFFs have no QN).
The cells are abutted into a continuous row with **`filltie`** cells between every cell and
**`endcap`** cells at the ends — these tie Nwell→VDD and Pwell→VSS (the std cells expose VNW/VPW
only as well layers, so without these taps the wells float and the cells don't work).

The DFF's Q sits on the right and CLK on the left, so the ripple chain hops with short clock wires.
The whole row is **horizontally mirrored** (`add_divider` places the cell with `x_reflection` +
180° rotation) so the ÷2 stage ends up on the **right** and ÷256 on the **left**, matching the
pin order. `add_divider` **centres** the row so the outputs reach the pin cluster with minimal fan.
The mapping is **LSB-first** — `uo_out[0]=÷2` .. `uo_out[7]=÷256`; because the mirror puts the stage
order in the same direction as the pin order, the eight output routes **fan straight down without
crossing** (the Metal3-track / Metal4-riser discipline still guards every remaining crossing — e.g.
the supply taps — but the divider taps themselves no longer cross). Each tap is `Q → riser → Metal3
jog (at its own horizontal track) → Metal4 pin-riser → pin`; the jog has to be Metal3 (it crosses
other taps' Metal4 pin-risers) and the pin-riser has to be Metal4 (it climbs past higher Metal3
jogs), but the short **flop-side** riser is kept on Metal3 rather than hopping up to Metal4 only to
drop straight back. That is possible because the eight horizontal tracks are not assigned in pin
order but **topologically ordered**: whenever one tap's flop sits under another's jog, the covering
jog is placed on a higher track, so no flop riser ever climbs through a jog. (For this fan that means
`uo_out[0]`'s jog sits *above* `uo_out[1]`/`[2]`'s.) The one obstacle a track order can't move is the
VDD strap — so VDD is tapped at the leftmost filltie, keeping its strap clear of every flop. The
mirror also frees the right
edge: the clock rises up it from the buffered `ua[0]` node and lands on the (now right-hand) CLK pin
directly — CLK and the reset `RN` both sit in the **clear channel just below the row** (between the
row at y≈300 and the ring top at y≈293), so the clock jogs across there and never excursions above
the row (no left-edge detour, no Metal3 dip). `osc_out` is no longer on a `uo_out` pin (the raw
oscillation is on `ua[0]`). The divider's VDD/VSS rails are
strapped to VDPWR/VGND on filltie columns (straps widened to 0.6 µm, 2-cut vias — cheap EM/IR
margin). **Watch the strap far-end:** it must use the *die* width (`2*cx`), not the local divider
width — an early version computed `VDPWR_X` from the divider width and the strap stopped in empty
space, leaving the std-cell rails floating (only the testbench's old force-tie hid it).

Post-layout SPICE confirms **/2 .. /256** (≈60 / 30 / 15 / 7.5 / 3.7 / 1.9 / 0.94 / 0.47 MHz from
the ≈120 MHz ring).

## The ua[0] output buffer (`add_ua_buffer`)

`ua[0]` is driven through **one more SkullFET inverter** (a 3.3V device — the same as the ring,
recovered by remapping the original `skullfet_inverter` cell, committed as `gds/skull_buffer.gds`)
placed in the clear bottom strip and powered from the left stripes along the bottom edge:
ring OSC → buffer → `ua[0]` (and the divider clock, which taps the buffered node). This isolates
the ring from any external load on `ua[0]`. Measured (swept cap on `ua[0]`): **without** the buffer
the ring frequency drops **−28 % at 1 pF, −62 % at 10 pF** (loading the OSC node directly distorts
the very oscillation you're observing); **with** it the ring stays at ~120 MHz across 0→10 pF. The
buffer's own output swing still falls under heavy load (a single inverter), but the ring — and the
frequency you read — is protected; the low divider taps remain the clean amplitude observation
points.

## LVS (`make lvs`)

`scripts/run_lvs.sh` extracts the layout with magic and runs **netgen** against an intended
structural source netlist (`scripts/gen_lvs_source.py`). netgen reports matching **device counts
(60 = 60)** and matching **net counts (329 = 329)**, and the device classes are equivalent
(`nfet_03v3 (22)`, `pfet_03v3 (22)`, 8× `dffrnq_1`, 8× `inv_2`) — 21 ring inverters + the `ua[0]`
buffer give the 22 nfet/22 pfet, and the 8-stage divider gives the 8 DFF + 8 inverter toggles. The
residual "top-level pin matching" note is netgen reconciling the **black-boxed std-cell pins**
against the flattened layout, plus the unused outputs `uio_out[7:0]`/`uio_oe[7:0]` which are **tied
to VGND** in the layout (so they collapse into the VGND net rather than presenting as 16 distinct
pins) — not a connectivity error. Treat this as a strong **device- and net-count cross-check**; a
fully signed-off LVS would flatten
the std-cell subckts on both sides. The authoritative functional check is the un-forced post-layout
simulation.

**Well/body connectivity — verified, nothing floats.** Every pfet body ties to VDPWR through the
skull inverter's n-well tap (preserved by the pSD-based implant regeneration above), the nfet
bodies tie to VGND, and the std-cell rails are strapped to VDPWR/VGND. The extraction contains **no
floating `w_*` well nets**, which is also why removing the simulation force-tie left the frequency
essentially unchanged (~120 MHz).

## SPICE / xschem (gf180)

All schematic-entry and testbench files are retargeted to gf180mcuD:

- `xschem/xschemrc` sources the gf180mcuD xschemrc; `xschem/skullfet_inverter.sch` uses
  `pfet_03v3`/`nfet_03v3` (W=5.87µm L=0.58µm, matching the layout); `xschem/testbench.sch` and
  `xschem/simulation/testbench.spice` use the gf180 ngspice models
  (`design.ngspice` + `sm141064.ngspice typical`), a **3.3V** supply and **1.65V** measurement
  thresholds. `spice/testbench.spice` is a gf180 testbench (3.3V, `make spice/pdk_lib.spice`
  generates the model include).
- **One caveat:** gf180mcuD ships **no std-cell xschem symbols**, and its DFFs have no QN output,
  so the divider *schematic* (`xschem/freq_divider.sch`) cannot be a 1:1 port of the IHP
  `sg13g2_dfrbp_2` toggle. The authoritative gf180 divider is the **layout** generator
  `scripts/build_divider.py` (dffrnq_1 + inv_2 toggle stages), verified end-to-end in post-layout
  SPICE (`make sim`) and netgen LVS (`make lvs`).

The canonical re-simulation is **`make sim`** (`scripts/sim_ring.sh`): it extracts the hardened
GDS, ties the std-cell wells/substrate, drives 3.3V, and reports osc_out + osc_div_2/4/8.
