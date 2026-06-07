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
- **TT precheck structural checks pass** (run locally against `tt-support-tools/precheck`):
  KLayout Checks (top name / no forbidden Metal5 / PR_bndry present), Boundary check, Layer check
  (only valid gf180 layers), Cell name check, Power pin check (VGND/VDPWR with USE in LEF + Verilog),
  Analog pin check (`ua[0]` connected), Pin check (all pins match the DEF template).
- **Verilog syntax check** passes (yosys).
- Config migrated: `info.yaml` (analog_pins: 1, `ua[0]=osc_out_3v3`, `uses_vapwr: false`),
  workflows (`@ttgf26a`, `pdk: gf180mcuD`), `src/project.v` (VGND/VDPWR ports), `Makefile`.

The KLayout FEOL/BEOL/offgrid/antenna decks need the KLayout binary (not the Python module) and
run in CI; magic DRC — the heaviest precheck — is clean locally.

## Remaining functional finalisation ⚠️

The macro is structurally submittable and DRC-clean, but the following net-level work needs the
designer's topology knowledge to make it fully functional:

1. **Oscillator output tap.** `ua[0]` and the `uo_out[*]` pins are currently routed to the ring's
   *outer power ring*, not to a live oscillating inter-stage node. Tap an actual inter-stage node
   (a Metal3 node between two adjacent inverters) and route it to `uo_out[0]` (and `ua[0]` for the
   raw 3.3V output). This is best done by keeping the inverter hierarchy / net names rather than
   the flattened ring.
2. **Frequency divider.** The original /2 /4 /8 divider used IHP `sg13g2_dfrbp_2` DFFs. These are
   not yet in the gf180 macro. Substitute gf180 std-cell DFFs (e.g. `gf180mcu_fd_sc_mcu7t5v0__dffrnq_1`
   from the PDK), place + re-wire 3 stages clocked by `osc_out`, reset by `rst_n`, outputs to
   `uo_out[1..3]`. (These are pre-built DRC-clean cells — place unscaled, do not 1.45× them.)
3. **Power connectivity / LVS.** The two concentric power rings (inner r≈93 µm = one supply, outer
   r≈128 µm = the other) are connected to the VGND/VDPWR stripes best-effort; verify which ring is
   VGND vs VDPWR against the inverter orientation and run LVS (netgen) to confirm connectivity.
4. **Simulation.** Re-extract SPICE (`make spice`) and simulate to characterise the new gf180
   oscillation frequency; update `docs/info.md` and regenerate `docs/layout_sim.png`.
5. **xschem / spice testbench** (`xschem/`, `spice/testbench.spice`) still reference IHP device
   symbols/models and need updating to gf180 (`pfet_03v3`/`nfet_03v3`, gf180 ngspice models) for
   the simulation cross-check.
