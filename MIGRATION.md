# Migration notes: IHP sg13g2 → gf180mcu

This project was migrated from IHP sg13g2 (`ttihp26a`) to **gf180mcuD** for the **ttgf0p3**
experimental shuttle, using the [ttgf-analog-template](https://github.com/TinyTapeout/ttgf-analog-template)
conventions and the `tt-support-tools/tech/gf180mcuD/def/analog` frame.

## Approach

The design is a hand-drawn analog macro (a ring of skull-shaped SkullFET transistors), so this is
a **layout-level port**, not a config swap. The skull artwork is preserved verbatim; the IHP layer
stack, device implants and feature sizes are retargeted to gf180mcuD in a pure-Python pipeline.

### The SkullFET device recipe (`scripts/remap_to_gf180.py`)

- **Layer remap** (IHP → gf180mcuD): Activ→COMP (22/0), GatPoly→Poly2 (30/0), Cont→Contact (33/0),
  Metal1-4 → 34/36/42/46, Via1/2/3/4 → 35/38/40/41, NWell→Nwell (21/0). The IHP 7-metal stack
  collapses to gf180's 4 usable routing metals (Metal5/81 is forbidden, MetalTop unreachable):
  M5/TopMetal1/TopMetal2 fold onto Metal4.
- **3.3V devices — no Dualgate.** This is the key insight. Marking Dualgate(55/0) makes magic
  extract the FETs as **6V medium-voltage** devices (gate ≥ 0.55/0.70 µm), which would force a
  ~2.5× blow-up that no longer fits the die. As plain **3.3V devices** (nfet_03v3/pfet_03v3, no
  Dualgate) the gate minimum is 0.28 µm — matching the 3.3V core supply.
- **Implant regeneration**: Pplus = COMP ∩ Nwell (+0.16 µm), Nplus = COMP − Nwell (+0.16 µm),
  LVPWELL over the NMOS region; Nwell grown +0.30 µm for the DF.7 p-diff overlap rule.
- **1.45× uniform scale** — the minimum that clears every 180nm width/spacing/cut rule.

Result: the full skull ring (21 inverters + central skull + power rings) remaps to a
**261 × 261 µm, 0-DRC-violation** block.

### Macro assembly (`scripts/build_gf180_macro.py`)

Builds `tt_um_oscillating_bones` (346.64 × 325.36 µm, 1×2 tile) from the TT analog DEF: all 51
Metal4 signal pins at the template positions, VGND/VDPWR Metal4 power stripes, the PR_bndry (0/0)
die outline, and the skull ring placed in the centre. Emits the matching LEF (correct SIZE,
`DIRECTION`, `USE POWER`/`USE GROUND`).

## What is validated ✅

- **Magic DRC: 0 violations** (full macro).
- **Post-layout SPICE oscillates.** Extracting the hardened GDS with magic and simulating with the
  gf180mcuD ngspice models, the 21-stage ring oscillates **rail-to-rail at ~122 MHz**, and the raw
  oscillation reaches the **`ua[0]` (osc_out_3v3)** pin. The extracted netlist is a clean, closed
  21-stage CMOS ring with **VGND and VDPWR as separate supplies** (21 transistors each), each driven
  by its power stripe. (Reproduce with `scripts/sim_ring.sh` — see below — or `make spice` + ngspice.)
- **TT precheck structural checks pass** (run locally against `tt-support-tools/precheck`):
  KLayout Checks, Boundary check, Layer check, Cell name check, Power pin check, Analog pin check,
  Pin check.
- **Verilog syntax check** passes (yosys).
- Config migrated: `info.yaml`, workflows (`@ttgf26a`, `pdk: gf180mcuD`), `src/project.v`, `Makefile`.

Two key fixes were needed to get the post-layout netlist to oscillate: (a) the inverter cells
carried decorative power-ring stubs on the upper metals that, after the 7→4 metal collapse, shorted
each inverter's VGND to VDPWR — these are dropped in the remap; (b) the per-inverter A/Y pin labels
must NOT be carried into the flattened ring (they would merge all inputs/outputs); inter-stage
connectivity is geometric. The macro's two power stripes sit on opposite die edges so their Metal4
connectors don't cross the other stripe.

The KLayout FEOL/BEOL/offgrid/antenna decks need the KLayout binary (not the Python module) and run
in CI; magic DRC runs clean locally.

## Remaining functional finalisation ⚠️

1. **Digital outputs `uo_out[0..3]`.** Only `ua[0]` is wired today. Route the OSC node (the Metal4
   tap the remap creates) to `uo_out[0]` (osc_out), and add the divider for `uo_out[1..3]`.
2. **Frequency divider.** The original /2 /4 /8 divider used IHP `sg13g2_dfrbp_2` DFFs, not yet in
   the gf180 macro. Substitute gf180 std-cell DFFs (e.g. `gf180mcu_fd_sc_mcu7t5v0__dffrnq_1`), place
   + re-wire 3 stages clocked by osc_out, reset by `rst_n`. (Pre-built DRC-clean cells — place
   unscaled, do not 1.45× them.)
3. **LVS.** Run netgen LVS of the extracted netlist against a schematic to formally confirm
   connectivity.
4. **xschem / spice testbench** (`xschem/`, `spice/testbench.spice`) still reference IHP device
   symbols/models; update to gf180 (`pfet_03v3`/`nfet_03v3`, gf180 ngspice models).
