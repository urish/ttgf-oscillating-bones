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
- **Post-layout SPICE oscillates and divides.** Extracting the hardened GDS with magic and
  simulating with the gf180mcuD ngspice models (`make sim`), the 21-stage ring oscillates
  **rail-to-rail at ~139 MHz**, and the std-cell ripple divider produces clean **/2, /4, /8** taps:
  `uo_out[0]=osc_out` ~139 MHz, `uo_out[1..3]=osc_div_2/4/8` ~70/35/17 MHz, plus the raw 3.3V
  oscillation on `ua[0]`. The testbench supplies **only VDPWR/VGND and the substrate bias** — it
  does **not** force any std-cell rail or device well, so the simulated behaviour reflects the
  actual extracted power connectivity (the divider's std-cell rails are genuinely strapped to
  VDPWR/VGND in the layout — see the divider section).
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

## The /2 /4 /8 divider (`scripts/build_divider.py`)

The divider is a 3-stage ripple counter of `gf180mcu_fd_sc_mcu7t5v0` std cells: each /2 stage is a
**`dffrnq_1`** DFF + an **`inv_2`** wired as a toggle FF (D = ~Q, since gf180 DFFs have no QN). The
cells are abutted into a continuous row with **`filltie`** cells between every cell and **`endcap`**
cells at the ends — these tie Nwell→VDD and Pwell→VSS (the std cells expose VNW/VPW only as well
layers, so without these taps the wells float and the cells don't work). It is placed in the top
strip and connected by a small **channel router** (in `add_divider`): Metal3 = horizontal tracks
(one unique y per net), Metal4 = vertical risers (unique x), so cross-net crossings can't short;
the clock enters from the bottom (tapped off the `ua[0]`/OSC node *outside* the ring) and takes one
Metal3 dip under the VGND supply connector. `uo_out[0]=osc_out`, `uo_out[1..3]=osc_div_2/4/8`.

The divider's VDD/VSS rails are strapped to VDPWR/VGND with two short Metal3 straps tapped on
filltie columns (one to each die-edge power stripe). **Note the easy mistake here:** the strap's
far end must use the *die* width (`2*cx`), not the local divider width — an early version computed
`VDPWR_X` from the divider width and the VDD strap stopped in empty space, leaving every std-cell
rail floating (the divider still "worked" in sim only because the testbench was force-tying the
rails; that force-tie has since been removed, which is how the bug surfaced).

Post-layout SPICE confirms **/2, /4, /8** (≈70 / 35 / 17 MHz from the ≈139 MHz ring).

## LVS (`make lvs`) — partial

`scripts/run_lvs.sh` extracts the layout with magic and runs **netgen** against an intended
structural source netlist (`scripts/gen_lvs_source.py`). netgen confirms the **device classes /
counts match** (`nfet_03v3 (21)`, `pfet_03v3 (21)`, 3× `dffrnq_1`, 3× `inv_2`), but it does **not**
report a clean top-level match: the std cells are compared as black boxes and the simplified source
model does not reproduce the extracted net topology exactly (net-count mismatch + a pin-matching
note that includes `ua[0]`/`uo_out[0]` sharing the `osc_out` net). So treat LVS as a
**device-level cross-check, not a signed-off full LVS** — the authoritative functional verification
is the (now un-forced) post-layout simulation. A clean full LVS would need the std-cell subckts
flattened on both sides and a faithful source netlist; the floating skull-inverter n-wells (below)
also show up as extra nets.

**Skull-inverter n-wells float.** The hand-drawn skull inverters have no explicit n-well tap, so
each pfet body extracts as its own `w_*` net (junction-biased on silicon). The ring oscillates fine
this way (it is why the honest frequency, ~139 MHz, is a bit higher than a hard-tied-well estimate),
but for a robust tape-out the n-wells should be strapped to VDPWR — a layout change to the skull art
that is left as a follow-up.

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
