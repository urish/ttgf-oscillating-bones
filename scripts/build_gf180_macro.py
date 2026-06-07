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
import os
import re
import sys
import math
import gdstk
import build_divider as BD

# gf180 layers
M4, M4PIN = (46, 0), (46, 10)
M3 = (42, 0)
M2 = (36, 0)
M1 = (34, 0)
VIA3, VIA2, VIA1 = (40, 0), (38, 0), (35, 0)
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


def via_m4_m3(cell, x, y):
    """M4<->M3 connection: M4 + M3 landing pads (1.0um) with a 2x2 Via3 array (0.26 cuts)."""
    s = VIA_SZ / 2
    pad = 0.7
    for lay in (M4, M3):
        cell.add(gdstk.rectangle((x - pad, y - pad), (x + pad, y + pad), layer=lay[0], datatype=lay[1]))
    for dx in (-0.28, 0.28):
        for dy in (-0.28, 0.28):
            cell.add(gdstk.rectangle((x + dx - s, y + dy - s), (x + dx + s, y + dy + s),
                                     layer=VIA3[0], datatype=VIA3[1]))


def _wire(cell, pts, w=0.4, layer=M4):
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        xa, xb = sorted((x0, x1)); ya, yb = sorted((y0, y1))
        cell.add(gdstk.rectangle((xa - w / 2, ya - w / 2), (xb + w / 2, yb + w / 2),
                                 layer=layer[0], datatype=layer[1]))


def _via(cell, x, y, layers, m1=True):
    """Stacked via through the given metal layers (e.g. [M1,M2,M3,M4]) at (x,y). Pads are
    small (0.46) to clear dense std-cell metal; set m1=False to skip the Metal1 pad when the
    landing is a std-cell pin that already provides Metal1."""
    cuts = {(M1, M2): VIA1, (M2, M3): VIA2, (M3, M4): VIA3}
    s, p = 0.13, 0.23
    for lay in layers:
        if lay == M1 and not m1:
            continue
        cell.add(gdstk.rectangle((x - p, y - p), (x + p, y + p), layer=lay[0], datatype=lay[1]))
    for a, b in zip(layers, layers[1:]):
        cut = cuts[(a, b)]
        cell.add(gdstk.rectangle((x - s, y - s), (x + s, y + s), layer=cut[0], datatype=cut[1]))


def add_divider(lib, top, pins, cx, cy, H, osc_xy):
    """Place a /2/4/8 std-cell divider in the top strip and wire it up."""
    pdk_root = os.environ.get("PDK_ROOT", "")
    divcell, dp, std_cells = BD.build_divider(BD.STD_GDS_DEFAULT, pdk_root)
    inv = std_cells[1]                       # inv_2, reused as the clock isolation buffer
    lib.add(divcell, *std_cells)
    DX0, DY0 = 95.0, 300.0     # Q columns sit left of the uo_out pins so output routes fan right
    top.add(gdstk.Reference(divcell, (DX0, DY0)))

    # --- clock isolation buffer (inv_2) in the bottom strip, below the ring ---
    # The ring's single OSC node cannot drive the long clock route + 5V DFF load without its
    # oscillation collapsing, so we buffer it: ring -> short hop -> buffer -> everything else.
    INV2_W = 3.36
    W_RIGHT = 2 * cx - 5.0                    # near the VDPWR stripe (right edge)
    ox0, oy0 = osc_xy
    BX, BY = ox0 - 1.4, 10.0                  # buffer placement (bottom strip)
    top.add(gdstk.Reference(inv, (BX, BY)))
    bI = (BX + 1.39, BY + 1.91)               # inv_2 I pin
    bZ = (BX + 1.44, BY + 3.00)               # inv_2 ZN pin (buffered, inverted osc)
    # power the buffer: VSS rail -> VGND stripe (left), VDD rail -> VDPWR stripe (right)
    _wire(top, [(5.0, BY + 0.0), (BX, BY + 0.0)], w=0.6, layer=M2)
    _via(top, 5.0, BY + 0.0, [M1, M2, M3, M4]); _via(top, BX, BY + 0.0, [M1, M2])
    _wire(top, [(BX + INV2_W, BY + 3.92), (W_RIGHT, BY + 3.92)], w=0.6, layer=M2)
    _via(top, W_RIGHT, BY + 3.92, [M1, M2, M3, M4]); _via(top, BX + INV2_W, BY + 3.92, [M1, M2])
    # ring OSC (M4) -> short hop down to the buffer input
    _wire(top, [(ox0, oy0), (ox0, bI[1]), (bI[0], bI[1])], w=0.4, layer=M4)
    _via(top, *bI, [M1, M2, M3, M4], m1=False)
    # buffer output (ZN) becomes the clock source for the spine
    _via(top, *bZ, [M1, M2, M3, M4], m1=False)
    osc_xy = bZ                               # downstream clock/divider drive from the buffer

    def P(name):  # divider pin -> macro coords
        v = dp[name]
        return (DX0 + v[0], DY0 + v[1])

    W = dp["_width"]
    pinrect = {n: r for (n, d, r) in pins}
    pin_cx = lambda n: (pinrect[n][0] + pinrect[n][2]) / 2

    # power straps: VSS rail -> VGND stripe (left); VDD rail -> VDPWR stripe (right)
    vss_y = DY0 - 0.0
    _wire(top, [(5.0, vss_y), (DX0 + 2, vss_y)], w=0.6, layer=M2)
    _via(top, 5.0, vss_y, [M1, M2, M3, M4]); _via(top, DX0 + 2, vss_y, [M1, M2])
    vdd_y = DY0 + 3.9
    vdd_tap = DX0 + 78.0     # in the last inter-cell gap (clear VDD rail bridge)
    _wire(top, [(vdd_tap, vdd_y), (cx + 168, vdd_y)], w=0.6, layer=M2)
    _via(top, cx + 168, vdd_y, [M1, M2, M3, M4]); _via(top, vdd_tap, vdd_y, [M1, M2])
    # well taps: tie nwell (VDD strap) and pwell (VSS strap) regions
    # (the std-cell VDD/VSS M1 rails already overlap VNW/VPW; the straps bias them)

    # clock: OSC (M4) -> down below the ring -> up the right edge on M3 -> divider CLK
    ox, oy = osc_xy
    clk_x = cx + 138.0          # right of the ring (ring outer ~cx+130)
    _wire(top, [(ox, oy), (ox, 25.0), (clk_x, 25.0)], w=0.4, layer=M4)
    _via(top, clk_x, 25.0, [M3, M4])
    _wire(top, [(clk_x, 25.0), (clk_x, DY0 + 8.0)], w=0.4, layer=M3)   # M3 clock spine
    ck = P("CLK")
    _wire(top, [(clk_x, DY0 + 1.96), (ck[0], DY0 + 1.96), ck], w=0.4, layer=M3)
    _via(top, *ck, [M2, M3])

    # osc_out -> uo_out[0]: branch off the clock at the top
    u0 = pin_cx("uo_out[0]")
    _wire(top, [(clk_x, DY0 + 8), (u0, DY0 + 8), (u0, pinrect["uo_out[0]"][1])], w=0.4, layer=M4)
    _via(top, clk_x, DY0 + 8, [M3, M4])

    # reset: rst_n pin -> divider RN
    rn = P("RN")
    rx = pin_cx("rst_n")
    _wire(top, [(rx, pinrect["rst_n"][1]), (rx, DY0 - 2.2), (rn[0], DY0 - 2.2), rn], w=0.4, layer=M3)
    _via(top, rx, pinrect["rst_n"][1] - 0.2, [M3, M4])
    _via(top, *rn, [M2, M3])

    # outputs DIV2/DIV4/DIV8 -> uo_out[1..3]. The divider Qs are ordered left->right but the
    # pins right->left, so the nets must cross: route each on a unique-y M3 horizontal track
    # with M4 verticals (Q->track and track->pin) so crossings are M3-over-M4 (no shorts).
    for j, (k, pin) in enumerate((("DIV2", "uo_out[1]"), ("DIV4", "uo_out[2]"), ("DIV8", "uo_out[3]"))):
        qx, qy = P(k)
        trk = DY0 + 11 + 3 * j
        tx = pin_cx(pin)
        _via(top, qx, qy, [M2, M3, M4])          # Q (M2) up to M4
        _wire(top, [(qx, qy), (qx, trk)], w=0.4, layer=M4)
        _via(top, qx, trk, [M3, M4])             # to the M3 track
        _wire(top, [(qx, trk), (tx, trk)], w=0.4, layer=M3)
        _via(top, tx, trk, [M3, M4])             # back up to M4 at the pin column
        _wire(top, [(tx, trk), (tx, pinrect[pin][1])], w=0.4, layer=M4)


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

    # --- power stripes + connections to the SkullFET supply pads ---
    # The inverters' VGND/VDPWR pads (Metal3, labelled in the ring) ARE the supply nets.
    # We connect a left-edge Metal4 stripe to one such pad per supply with a Metal4 connector
    # (which passes harmlessly over the Metal3 outer ring) + a via3 landing on the pad. Reading
    # the actual label positions guarantees we hit the correct net (no inner/outer guesswork).
    def supply_pad(text, target_angle):
        """The VGND/VDPWR pad nearest target_angle (deg), in macro coordinates."""
        cands = []
        for lb in ring.labels:
            if lb.text == text:
                a = math.degrees(math.atan2(lb.origin[1], lb.origin[0])) % 360
                da = min(abs(a - target_angle), 360 - abs(a - target_angle))
                cands.append((da, lb.origin[0] + cx, lb.origin[1] + cy))
        cands.sort()
        return cands[0][1], cands[0][2]

    # VGND stripe on the LEFT edge -> a VGND pad on the left side (angle ~180).
    # VDPWR stripe on the RIGHT edge -> a VDPWR pad on the right side (angle ~0).
    # Opposite sides so neither horizontal Metal4 connector crosses the other vertical stripe.
    supply = {"VGND": (3.0 + STRIPE_W / 2, 180.0), "VDPWR": (W - 3.0 - STRIPE_W / 2, 0.0)}
    pad_pos = {}
    for name, (x, ang) in supply.items():
        x1, x2 = x - STRIPE_W / 2, x + STRIPE_W / 2
        top.add(gdstk.rectangle((x1, 5.0), (x2, H - 5.0), layer=M4[0], datatype=M4[1]))
        top.add(gdstk.rectangle((x1, 5.0), (x2, H - 5.0), layer=M4PIN[0], datatype=M4PIN[1]))
        top.add(gdstk.Label(name, (x, cy), layer=M4PIN[0], texttype=M4PIN[1]))
        px, py = supply_pad(name, ang)
        pad_pos[name] = (px, py)
        xa, xb = sorted((x1 if ang > 90 else x2, px))
        top.add(gdstk.rectangle((xa, py - 0.6), (xb, py + 0.6), layer=M4[0], datatype=M4[1]))
        via_m4_m3(top, px, py)

    # --- analog output ua[0] = osc_out_3v3: tap the live OSC node (a ring inter-stage output
    # brought up to Metal4 + labelled "OSC" by the remap) and route it to the ua[0] pin.
    osc_xy = None
    for lb in ring.labels:
        if lb.text == "OSC":
            osc_xy = (lb.origin[0] + cx, lb.origin[1] + cy)
    ua0 = next(r for (n, d, r) in pins if n == "ua[0]")
    ua0_cx = (ua0[0] + ua0[2]) / 2
    if osc_xy:
        ox, oy = osc_xy
        # L-route on Metal4: up from ua[0] to the OSC y, then across to OSC x
        top.add(gdstk.rectangle((ua0_cx - 0.5, ua0[1]), (ua0_cx + 0.5, oy + 0.5), layer=M4[0], datatype=M4[1]))
        x_lo, x_hi = sorted((ua0_cx, ox))
        top.add(gdstk.rectangle((x_lo, oy - 0.5), (x_hi, oy + 0.5), layer=M4[0], datatype=M4[1]))

    # === /2 /4 /8 divider (uo_out[1..3]) + osc_out (uo_out[0]) ===
    if osc_xy:
        add_divider(lib, top, pins, cx, cy, H, osc_xy)

    lib.write_gds(out_gds)
    bb = top.bounding_box()
    print(f"wrote {out_gds}: tt_um_oscillating_bones {bb[1][0]-bb[0][0]:.2f} x {bb[1][1]-bb[0][1]:.2f} um, "
          f"{len(pins)} signal pins + VGND/VDPWR")

    # --- write the matching LEF (precheck wants correct SIZE + USE POWER/GROUND) ---
    lef_path = out_gds.replace("gds/", "lef/").replace(".gds", ".lef")
    write_lef(lef_path, W, H, pins,
              vdpwr=(W - 3.0 - STRIPE_W, 5.0, W - 3.0, H - 5.0),
              vgnd=(3.0, 5.0, 3.0 + STRIPE_W, H - 5.0))
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
