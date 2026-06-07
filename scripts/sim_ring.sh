#!/usr/bin/env bash
# Post-layout simulation of the SkullFET ring oscillator.
#   - extracts gds/tt_um_oscillating_bones.gds with magic (device-level netlist)
#   - ties the n-wells to VDPWR and the substrate to VGND
#   - drives VDPWR=3.3V, VGND=0 and runs a transient with ngspice + gf180mcuD models
#   - reports the oscillation frequency seen on the ua[0] (osc_out_3v3) pin
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

# flatten the subckt, tie wells/substrate/std-cell power, sanitise net names for ngspice
grep -vE '^\.subckt|^\.ends' "$OUT/macro.spice" \
  | sed -E 's/[A-Za-z0-9_./]+\.(VNW|VDD|VDPWR)\b/VDPWR/g; s/[A-Za-z0-9_./]+\.(VPW|VSS|VGND)\b/VGND/g;
            s/w_[a-z0-9_]+#?/VDPWR/g; s/\bVSUBS\b/VGND/g; s/#//g; s/\[([0-9]+)\]/_\1/g' \
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
.tran 10p 400n uic
.control
run
wrdata $OUT/osc.txt v(uo_out_0) v(uo_out_1) v(uo_out_2) v(uo_out_3)
quit
.endc
.end
EOF

ngspice -b "$OUT/tb.spice" >/dev/null 2>&1 || true

python3 - "$OUT/osc.txt" <<'PY'
import numpy as np, sys, os
p=sys.argv[1]
if not os.path.exists(p): print("simulation produced no output"); sys.exit(1)
d=np.loadtxt(p); t=d[:,0]
base=None
for nm, c in (("uo_out[0] osc_out", 1), ("uo_out[1] osc_div_2", 3),
              ("uo_out[2] osc_div_4", 5), ("uo_out[3] osc_div_8", 7)):
    v=d[:, c]; mid=(v.max()+v.min())/2
    cr=np.where((v[:-1]<mid)&(v[1:]>=mid))[0]; cr=cr[t[cr] > 150e-9]
    f=(1/np.median(np.diff(t[cr]))/1e6) if len(cr) >= 3 else 0
    if base is None and f: base=f
    ratio=f"  (osc/{base/f:.0f})" if (f and base and c > 1) else ""
    print(f"{nm:22s} {v.min():.2f}..{v.max():.2f} V  {f:6.1f} MHz{ratio}")
PY
