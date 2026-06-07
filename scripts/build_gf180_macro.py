#!/usr/bin/env python3
"""
Assemble the full gf180mcuD macro `tt_um_oscillating_bones` for Tiny Tapeout.

Frame comes from the TT analog template DEF (die outline + Metal4 signal-pin
positions); the DRC-clean remapped SkullFET ring (scripts/remap_to_gf180.py) is
placed in the centre; VGND/VDPWR Metal4 power stripes are added (matching the
official magic_init_project.tcl convention) and connected to the ring's two
concentric power rings; the analog output ua[0] is tapped to the ring.

This produces gds/tt_um_oscillating_bones.gds.  The LEF and SPICE are then written
by magic (see Makefile).

Usage: build_gf180_macro.py <ring.gds> <def> <out.gds>
"""
import re
import sys
import math
import gdstk

# gf180 layers
M4, M4PIN = (46, 0), (46, 10)
M3 = (42, 0)
M2 = (36, 0)
VIA3, VIA2 = (40, 0), (38, 0)
PR_BNDRY = (0, 0)   # gf180mcuD "PR_bndry" — required by precheck, must enclose the macro
U = 2000.0  # DEF database units per micron

# Power stripe geometry
STRIPE_W = 4.0          # um (>= 0.8 min); generous for low-resistance power
VIA_SZ = 0.26           # via cut size (gf180 Via2/Via3 ~0.26-0.28)


def parse_def(def_path):
    txt = open(def_path).read()
    die = re.search(r"DIEAREA \( 0 0 \) \( (\d+) (\d+) \)", txt)
    W, H = int(die.group(1)) / U, int(die.group(2)) / U
    pat = re.compile(
        r"- (\S+) \+ NET \S+ \+ DIRECTION (\w+).*?LAYER Metal4 "
        r"\( (-?\d+) (-?\d+) \) \( (-?\d+) (-?\d+) \).*?PLACED \( (\d+) (\d+) \)",
        re.S)
    pins = []
    for nm, d, x1, y1, x2, y2, px, py in pat.findall(txt):
        px, py = int(px) / U, int(py) / U
        rx1, ry1, rx2, ry2 = (int(v) / U for v in (x1, y1, x2, y2))
        pins.append((nm, d, (px + rx1, py + ry1, px + rx2, py + ry2)))
    return W, H, pins


def add_pin(cell, name, rect):
    x1, y1, x2, y2 = rect
    cell.add(gdstk.rectangle((x1, y1), (x2, y2), layer=M4[0], datatype=M4[1]))
    cell.add(gdstk.rectangle((x1, y1), (x2, y2), layer=M4PIN[0], datatype=M4PIN[1]))
    cell.add(gdstk.Label(name, ((x1 + x2) / 2, (y1 + y2) / 2), layer=M4PIN[0],
                         texttype=M4PIN[1]))


def via_stack_m4_m2(cell, x, y):
    """M4<->M2 via stack: M4/M3/M2 pads (0.6) enclosing Via3/Via2 cuts (0.26)."""
    s = VIA_SZ / 2
    pad = 0.3  # half-width of the metal landing pads -> 0.17um enclosure of the cut
    for lay in (M4, M3, M2):
        cell.add(gdstk.rectangle((x - pad, y - pad), (x + pad, y + pad), layer=lay[0], datatype=lay[1]))
    for lay in (VIA3, VIA2):
        cell.add(gdstk.rectangle((x - s, y - s), (x + s, y + s), layer=lay[0], datatype=lay[1]))


def build(ring_gds, def_path, out_gds):
    W, H, pins = parse_def(def_path)
    cx, cy = W / 2, H / 2

    lib = gdstk.read_gds(ring_gds)
    ring = lib.cells[0]
    rb = ring.bounding_box()
    r_outer = (rb[1][0] - rb[0][0]) / 2          # ring half-extent (~130.5)

    top = lib.new_cell("tt_um_oscillating_bones")
    # place ring centred
    top.add(gdstk.Reference(ring, (cx, cy)))

    # PR boundary = die outline
    top.add(gdstk.rectangle((0, 0), (W, H), layer=PR_BNDRY[0], datatype=PR_BNDRY[1]))

    # signal pins from DEF
    for nm, d, rect in pins:
        add_pin(top, nm, rect)

    # --- power stripes (vertical Metal4 bars), per magic_init convention ---
    # VDPWR stripe at the outer-ring left tangent so it contacts the OUTER ring.
    vdpwr_x = cx - 128 * 1.0   # outer power-ring radius in ring-local was 128 (already scaled)
    # (ring already scaled; its outer power ring sits at radius ~128 from centre)
    for name, x in (("VDPWR", cx - 128.0), ("VGND", 2.0 + STRIPE_W / 2)):
        x1, x2 = x - STRIPE_W / 2, x + STRIPE_W / 2
        top.add(gdstk.rectangle((x1, 5.0), (x2, H - 5.0), layer=M4[0], datatype=M4[1]))
        top.add(gdstk.rectangle((x1, 5.0), (x2, H - 5.0), layer=M4PIN[0], datatype=M4PIN[1]))
        top.add(gdstk.Label(name, (x, cy), layer=M4PIN[0], texttype=M4PIN[1]))

    # VGND -> inner ring (radius ~93) via a Metal2 underpass that ducks under the
    # outer ring, entering through the bottom gap (y below the ring) to avoid the
    # inverters which sit on the ring band.
    inner_r = 93.0
    # bottom tangent of inner ring:
    iy = cy - inner_r
    gx = cx
    via_stack_m4_m2(top, gx, iy + 1.0)                     # tap inner ring (M4) -> M2
    # M2 run from inner-ring bottom down to y=5, then left to the VGND stripe, then up
    top.add(gdstk.rectangle((gx - 0.3, 5.0), (gx + 0.3, iy + 1.0), layer=M2[0], datatype=M2[1]))
    top.add(gdstk.rectangle((2.0, 5.0), (gx + 0.3, 5.6), layer=M2[0], datatype=M2[1]))
    via_stack_m4_m2(top, 2.0 + STRIPE_W / 2, 5.3)          # M2 -> VGND stripe (M4)

    # --- analog output ua[0] -> tap the ring (outer edge), bottom-right ---
    ua0 = next(r for (n, d, r) in pins if n == "ua[0]")
    ua0_cx = (ua0[0] + ua0[2]) / 2
    # route Metal4 from ua[0] up to the ring outer edge near the bottom-right
    tap_x = cx + (r_outer - 2.0) * math.cos(math.radians(-35))
    tap_y = cy + (r_outer - 2.0) * math.sin(math.radians(-35))
    # L-route on Metal4: up from ua[0], then to tap
    top.add(gdstk.rectangle((ua0_cx - 0.4, ua0[1]), (ua0_cx + 0.4, tap_y), layer=M4[0], datatype=M4[1]))
    x_lo, x_hi = sorted((ua0_cx, tap_x))
    top.add(gdstk.rectangle((x_lo, tap_y - 0.4), (x_hi, tap_y + 0.4), layer=M4[0], datatype=M4[1]))

    lib.write_gds(out_gds)
    bb = top.bounding_box()
    print(f"wrote {out_gds}: tt_um_oscillating_bones {bb[1][0]-bb[0][0]:.2f} x {bb[1][1]-bb[0][1]:.2f} um, "
          f"{len(pins)} signal pins + VGND/VDPWR")

    # --- write the matching LEF (precheck wants correct SIZE + USE POWER/GROUND) ---
    lef_path = out_gds.replace("gds/", "lef/").replace(".gds", ".lef")
    write_lef(lef_path, W, H, pins,
              vdpwr=(cx - 128.0 - STRIPE_W / 2, 5.0, cx - 128.0 + STRIPE_W / 2, H - 5.0),
              vgnd=(2.0, 5.0, 2.0 + STRIPE_W, H - 5.0))
    print(f"wrote {lef_path}")


def write_lef(path, W, H, pins, vdpwr, vgnd):
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    use = {"INPUT": "SIGNAL", "OUTPUT": "SIGNAL", "INOUT": "SIGNAL"}
    lines = [
        "VERSION 5.7 ;", 'BUSBITCHARS "[]" ;', 'DIVIDERCHAR "/" ;', "",
        f"MACRO tt_um_oscillating_bones", "  CLASS BLOCK ;",
        "  FOREIGN tt_um_oscillating_bones 0 0 ;", "  ORIGIN 0 0 ;",
        f"  SIZE {W:.3f} BY {H:.3f} ;",
    ]

    def pin_block(name, direction, useclass, rect):
        x1, y1, x2, y2 = rect
        return [
            f"  PIN {name}",
            f"    DIRECTION {direction} ;",
            f"    USE {useclass} ;",
            "    PORT",
            "      LAYER Metal4 ;",
            f"        RECT {x1:.3f} {y1:.3f} {x2:.3f} {y2:.3f} ;",
            "    END",
            f"  END {name}",
        ]

    for nm, d, rect in pins:
        lines += pin_block(nm, d, use[d], rect)
    lines += pin_block("VDPWR", "INOUT", "POWER", vdpwr)
    lines += pin_block("VGND", "INOUT", "GROUND", vgnd)
    lines += [f"END tt_um_oscillating_bones", "", "END LIBRARY", ""]
    open(path, "w").write("\n".join(lines))


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2], sys.argv[3])
