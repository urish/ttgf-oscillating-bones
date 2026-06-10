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

# Power stripe geometry. Both stripes sit on the LEFT edge (VGND leftmost, VDPWR just inside it),
# matching the original IHP arrangement: the TT power grid enters from the left, so keeping both
# rails there means the connector strips don't reach across the skull. Stripes run y=5..H-5
# (~97% of die height, > the 90% the analog power pins must span).
STRIPE_W = 4.0          # um (>= 0.8 min); generous for low-resistance power
VGND_SX = 3.0           # VGND stripe left-x (leftmost die edge)
VDPWR_SX = 10.0         # VDPWR stripe left-x (next to VGND)
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
    """Place the N-stage /2../256 std-cell ripple divider centred in the top strip and wire it up.

    Centring makes each stage's output fan to the uo_out pin at the matching left->right position,
    so the N output routes don't cross: stage j (DIV2^(j+1)) -> uo_out[N-1-j] (so uo_out[0]=/256
    .. uo_out[N-1]=/2).  M3 = horizontal tracks (unique y), M4 = vertical risers (unique x).
    """
    pdk_root = os.environ.get("PDK_ROOT", "")
    divcell, dp, std_cells = BD.build_divider(BD.STD_GDS_DEFAULT, pdk_root)
    lib.add(divcell, *std_cells)
    W = dp["_width"]; N = dp["_nstages"]
    DX0, DY0 = round(cx - W / 2, 2), 300.0      # centred -> symmetric, non-crossing output fan
    top.add(gdstk.Reference(divcell, (DX0, DY0)))

    def P(name):
        v = dp[name]; return (DX0 + v[0], DY0 + v[1])
    pinrect = {n: r for (n, d, r) in pins}
    pin_cx = lambda n: (pinrect[n][0] + pinrect[n][2]) / 2
    def mvia(x, y): _via(top, x, y, [M3, M4])

    def beefy(x, y, layers):
        """Low-R power tap: a 2-cut (vertically stacked) via per layer transition. The single
        0.26um cut was the tightest link in the divider supply; doubling the cuts is cheap EM/IR
        insurance, and a 1-wide x 2-tall stack still fits the narrow 1.12um filltie column."""
        s = VIA_SZ / 2
        cuts = {(M1, M2): VIA1, (M2, M3): VIA2, (M3, M4): VIA3}
        for lay in layers:
            top.add(gdstk.rectangle((x - 0.4, y - 0.55), (x + 0.4, y + 0.55), layer=lay[0], datatype=lay[1]))
        for a, b in zip(layers, layers[1:]):
            cut = cuts[(a, b)]
            for dy in (-0.3, 0.3):
                top.add(gdstk.rectangle((x - s, y + dy - s), (x + s, y + dy + s),
                                        layer=cut[0], datatype=cut[1]))

    VGND_X, VDPWR_X = VGND_SX + STRIPE_W / 2, VDPWR_SX + STRIPE_W / 2
    rail_vss, rail_vdd = DY0, DY0 + 3.9
    PW = 0.6                                     # power strap width (50% wider than the old 0.4um)
    # inter-cell filltie columns (clear of the DFF Q risers) for the power taps
    ties = [DX0 + BD.CAP_W + BD.DFF_W + BD.TIE_W + BD.INV_W + BD.TIE_W / 2
            + j * (BD.DFF_W + 2 * BD.TIE_W + BD.INV_W) for j in range(N)]

    # --- power: VSS rail -> VGND stripe, VDD rail -> VDPWR stripe (both on the left edge) ---
    vss_tap, vdd_tap = ties[0], ties[1]
    beefy(vss_tap, rail_vss, [M1, M2, M3])
    _wire(top, [(vss_tap, rail_vss), (VGND_X, rail_vss)], w=PW, layer=M3)
    beefy(VGND_X, rail_vss, [M3, M4])
    beefy(vdd_tap, rail_vdd, [M1, M2, M3])
    _wire(top, [(vdd_tap, rail_vdd), (VDPWR_X, rail_vdd)], w=PW, layer=M3)
    beefy(VDPWR_X, rail_vdd, [M3, M4])

    # track plan: N output tracks above the row, clock on top, reset below the row
    t_out = [DY0 + 6.0 + 2.0 * j for j in range(N)]     # 306 .. 320
    t_clk = DY0 + 22.0                                   # 322
    t_rn = DY0 - 5.0                                     # 295 (below the row, above the ring)

    # --- clock: OSC up the left edge to CLK (leftmost stage), M3 dip across the two left-edge
    #     supply connectors (VDPWR ~138, VGND ~187) ---
    ua0r = next(r for (n, d, r) in pins if n == "ua[0]")
    tapx = (ua0r[0] + ua0r[2]) / 2
    csx = 20.0
    ck = P("CLK")
    _wire(top, [(tapx, 0.5), (tapx, 22.0), (csx, 22.0)], w=0.4, layer=M4)
    _wire(top, [(csx, 22.0), (csx, 134.0)], w=0.4, layer=M4)
    mvia(csx, 134.0); _wire(top, [(csx, 134.0), (csx, 192.0)], w=0.4, layer=M3)
    mvia(csx, 192.0); _wire(top, [(csx, 192.0), (csx, t_clk)], w=0.4, layer=M4)
    mvia(csx, t_clk); _wire(top, [(csx, t_clk), (ck[0], t_clk)], w=0.4, layer=M3)
    mvia(ck[0], t_clk); _wire(top, [(ck[0], t_clk), (ck[0], ck[1])], w=0.4, layer=M4)
    _via(top, ck[0], ck[1], [M2, M3, M4])

    # --- reset: rst_n pin -> RN, in the channel BELOW the row (clear of the outputs) ---
    rn = P("RN"); rx = pin_cx("rst_n")
    _wire(top, [(rx, pinrect["rst_n"][1]), (rx, t_rn)], w=0.4, layer=M4); mvia(rx, t_rn)
    _wire(top, [(rx, t_rn), (rn[0], t_rn)], w=0.4, layer=M3); mvia(rn[0], t_rn)
    _wire(top, [(rn[0], t_rn), (rn[0], rn[1])], w=0.4, layer=M4)
    _via(top, rn[0], rn[1], [M2, M3, M4])

    # --- N outputs: stage j (DIV2^(j+1)) -> uo_out[N-1-j], each on its own track (no crossing) ---
    for j in range(N):
        qx, qy = P(f"DIV{2 ** (j + 1)}")
        pin = f"uo_out[{N - 1 - j}]"
        tx, trk = pin_cx(pin), t_out[j]
        _via(top, qx, qy, [M2, M3, M4]); _wire(top, [(qx, qy), (qx, trk)], w=0.4, layer=M4)
        mvia(qx, trk); _wire(top, [(qx, trk), (tx, trk)], w=0.4, layer=M3)
        mvia(tx, trk); _wire(top, [(tx, trk), (tx, pinrect[pin][1])], w=0.4, layer=M4)


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

    # Both stripes on the LEFT edge: VGND leftmost, VDPWR just inside it (IHP arrangement). The
    # supply pads are picked on the left side at well-separated angles so their connectors sit at
    # different y. Each connector runs Metal4 OVER the Metal3 power rings to its pad; the VGND
    # connector also has to hop the VDPWR stripe, so it dips to Metal3 across it (outside the ring,
    # where there are no Metal3 rings to short against).
    supply = {"VGND": (VGND_SX + STRIPE_W / 2, 168.0), "VDPWR": (VDPWR_SX + STRIPE_W / 2, 192.0)}
    pad_pos = {}
    for name, (x, ang) in supply.items():
        x1, x2 = x - STRIPE_W / 2, x + STRIPE_W / 2
        top.add(gdstk.rectangle((x1, 5.0), (x2, H - 5.0), layer=M4[0], datatype=M4[1]))
        top.add(gdstk.rectangle((x1, 5.0), (x2, H - 5.0), layer=M4PIN[0], datatype=M4PIN[1]))
        top.add(gdstk.Label(name, (x, cy), layer=M4PIN[0], texttype=M4PIN[1]))
        px, py = supply_pad(name, ang)
        pad_pos[name] = (px, py)
        if name == "VGND":
            d0, d1 = VDPWR_SX - 1.0, VDPWR_SX + STRIPE_W + 1.0   # hop the VDPWR stripe on Metal3
            top.add(gdstk.rectangle((x2, py - 0.6), (d0, py + 0.6), layer=M4[0], datatype=M4[1]))
            via_m4_m3(top, d0, py)
            top.add(gdstk.rectangle((d0, py - 0.6), (d1, py + 0.6), layer=M3[0], datatype=M3[1]))
            via_m4_m3(top, d1, py)
            top.add(gdstk.rectangle((d1, py - 0.6), (px, py + 0.6), layer=M4[0], datatype=M4[1]))
        else:
            top.add(gdstk.rectangle((x2, py - 0.6), (px, py + 0.6), layer=M4[0], datatype=M4[1]))
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
              vdpwr=(VDPWR_SX, 5.0, VDPWR_SX + STRIPE_W, H - 5.0),
              vgnd=(VGND_SX, 5.0, VGND_SX + STRIPE_W, H - 5.0))
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
