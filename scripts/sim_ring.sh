#!/usr/bin/env bash
# Post-layout simulation of the SkullFET ring oscillator + /2/4/8 divider.
#   - extracts gds/tt_um_oscillating_bones.gds with magic (device-level netlist)
#   - drives VDPWR=3.3V, VGND=0 and runs a transient with ngspice + gf180mcuD models
#   - reports osc_out + osc_div_2/4/8 on uo_out[0..3]
#
# Power connectivity is taken AS EXTRACTED — the testbench only supplies VDPWR/VGND and biases
# the global substrate node; it deliberately does NOT force the std-cell rails or device wells,
# so a missing power route shows up as a broken sim (not silently patched). The std cells get
# VDPWR/VGND from the macro's power straps; the skull-inverter pfet n-wells have no explicit tap
# and float (junction-biased), which is why the honest ring frequency (~139 MHz) is a little
# higher than a hard-tied-well estimate.
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

# flatten the subckt and sanitise net names for ngspice. The ONLY net forced here is the global
# substrate (VSUBS -> VGND, the normal substrate bias); std-cell rails and device wells are left
# exactly as extracted so a missing power connection is not masked.
grep -vE '^\.subckt|^\.ends' "$OUT/macro.spice" \
  | sed -E 's/\bVSUBS\b/VGND/g; s/#//g; s/\[([0-9]+)\]/_\1/g' \
  > "$OUT/flat.spice"

# an internal inter-stage node to kick the oscillator out of its metastable point
NODE=$(python3 - "$OUT/flat.spice" <<'PY'
import re, sys
from collections import Counter
dev=[l.split() for l in open(sys.argv[1]) if re.match(r'^X\d', l)]
f=Counter()
for t in dev:
    for n in t[1:5]: f[n.split('.t')[0]] += 1
print(next(n for n,c in f.most_common() if c==4 and n.startswith('a_')))
PY
)

cat > "$OUT/tb.spice" <<EOF
* Post-layout SkullFET ring oscillator + /2/4/8 divider (gf180mcuD, 3.3V)
.include $NG/design.ngspice
.lib '$NG/sm141064.ngspice' typical
.include $OUT/flat.spice
Vdd VDPWR 0 3.3
Vss VGND 0 0
Vrst rst_n 0 PWL(0 0 12n 0 12.5n 3.3)
.option rshunt=1e9
.ic v($NODE)=0
.tran 20p 4.5u uic
.control
run
wrdata $OUT/osc.txt v(ua_0) v(uo_out_0) v(uo_out_1) v(uo_out_2) v(uo_out_3) v(uo_out_4) v(uo_out_5) v(uo_out_6) v(uo_out_7)
quit
.endc
.end
EOF

ngspice -b "$OUT/tb.spice" >/dev/null 2>&1 || true

python3 - "$OUT/osc.txt" <<'PY'
import numpy as np, sys, os
p=sys.argv[1]
if not os.path.exists(p): print("simulation produced no output"); sys.exit(1)
d=np.loadtxt(p); t=d[:, 0]
# col 1 = ua[0] (buffered raw osc = ring); cols 3,5.. = uo_out[0..7] = /2 /4 .. /256 (LSB first).
rows=[("ring (ua[0]=osc)", 1, "")]
for k in range(8):
    rows.append((f"uo_out[{k}] osc_div_{2**(k+1)}", 3 + 2*k, f"osc/{2**(k+1)}"))
base=None
for nm, c, lbl in rows:
    v=d[:, c]; mid=(v.max()+v.min())/2
    cr=np.where((v[:-1]<mid)&(v[1:]>=mid))[0]; cr=cr[t[cr] > 0.3e-6]
    f=(1/np.median(np.diff(t[cr]))/1e6) if len(cr) >= 2 else 0
    if base is None and f: base=f
    print(f"{nm:24s} {v.min():.2f}..{v.max():.2f} V  {f:8.3f} MHz  {lbl}")
PY
