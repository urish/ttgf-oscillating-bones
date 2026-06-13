#!/usr/bin/env bash
# Generate docs/layout_sim.png — a post-layout waveform plot of osc_out + the /2 /4 /8 divider
# taps. Extracts the hardened GDS with magic, ties only the global substrate (everything else as
# extracted, like `make sim`), runs ngspice, and renders the traces with matplotlib.
#
# Requires: PDK_ROOT pointing at a gf180mcuD install, and `magic` + `ngspice` on PATH.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PDK=gf180mcuD
NG="$PDK_ROOT/$PDK/libs.tech/ngspice"
RC="$PDK_ROOT/$PDK/libs.tech/magic/$PDK.magicrc"
OUT="$(mktemp -d)"

magic -dnull -noconsole -rcfile "$RC" "$ROOT/scripts/extract_sim.tcl" \
    "$ROOT/gds/tt_um_oscillating_bones.gds" "$OUT/macro.spice" tt_um_oscillating_bones >/dev/null

grep -vE '^\.subckt|^\.ends' "$OUT/macro.spice" \
  | sed -E 's/\bVSUBS\b/VGND/g; s/#//g; s/\[([0-9]+)\]/_\1/g' > "$OUT/flat.spice"

NODE=$(awk '/nfet_03v3/{print $3; exit}' "$OUT/flat.spice")
cat > "$OUT/tb.spice" <<EOF
* Post-layout waveform capture (gf180mcuD, 3.3V)
.include $NG/design.ngspice
.lib '$NG/sm141064.ngspice' typical
.include $OUT/flat.spice
Vdd VDPWR 0 3.3
Vss VGND 0 0
Vrst rst_n 0 PWL(0 0 12n 0 12.5n 3.3)
.option rshunt=1e9
.ic v($NODE)=0
.tran 5p 220n uic
.control
run
wrdata $OUT/wave.txt v(ua_0) v(uo_out_0) v(uo_out_1) v(uo_out_2)
quit
.endc
.end
EOF
ngspice -b "$OUT/tb.spice" >/dev/null 2>&1 || true

python3 "$ROOT/scripts/plot_wave.py" "$OUT/wave.txt" "$ROOT/docs/layout_sim.png"
