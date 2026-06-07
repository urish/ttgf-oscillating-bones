#!/usr/bin/env bash
# Netgen LVS: extract the hardened layout and compare it against the intended structural
# source netlist (scripts/gen_lvs_source.py).
#
# Requires: PDK_ROOT pointing at gf180mcuD, and `magic` + `netgen` on PATH. netgen is NOT in
# this sandbox image (only magic is) — run this in an environment with the full gf180 toolchain
# (e.g. the TT/openlane image) or `nix run nixpkgs#...netgen`.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PDK=gf180mcuD
RC="$PDK_ROOT/$PDK/libs.tech/magic/$PDK.magicrc"
SETUP="$PDK_ROOT/$PDK/libs.tech/netgen/${PDK}_setup.tcl"
OUT="$(mktemp -d)"

# 1) layout netlist (device-level, no parasitics)
magic -dnull -noconsole -rcfile "$RC" "$ROOT/scripts/extract_lvs.tcl" \
    "$ROOT/gds/tt_um_oscillating_bones.gds" "$OUT/layout.spice" tt_um_oscillating_bones >/dev/null

# 2) source (schematic) netlist
python3 "$ROOT/scripts/gen_lvs_source.py" "$OUT/source.spice"

# 3) compare with netgen
netgen -batch lvs \
    "$OUT/layout.spice tt_um_oscillating_bones" \
    "$OUT/source.spice tt_um_oscillating_bones" \
    "$SETUP" "$ROOT/lvs.report"

echo "LVS report: $ROOT/lvs.report"
tail -20 "$ROOT/lvs.report" 2>/dev/null || true
