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


SKULL_BUFFER_GDS = os.path.join(os.path.dirname(__file__), "..", "gds", "skull_buffer.gds")
# pin offsets relative to the placed skull-buffer origin (from the remapped cell)
BUF_A = (5.0, 0.29)         # input A  (land on the cell's Metal2 A-pad, clear of its gate vias)
BUF_Y = (-4.39, 0.29)       # output Y (Metal1 + Metal4 OSC tap)
BUF_VGND = (-4.46, 8.70)    # VGND pad (Metal3)
BUF_VDPWR = (-4.39, -8.45)  # VDPWR pad (Metal3)


def add_ua_buffer(lib, top, pins, osc_xy):
    """Place a SkullFET inverter as the ua[0] output buffer in the clear bottom strip and wire it:
    ring OSC -> A; Y -> ua[0] pin (which the divider clock also taps). Powered from the left
    stripes along the bottom edge. A 3.3V SkullFET (same device as the ring) decouples the ring
    from any external load on ua[0]."""
    buf = gdstk.read_gds(SKULL_BUFFER_GDS).cells[0]
    lib.add(buf)
    BX, BY = 300.0, 15.0
    top.add(gdstk.Reference(buf, (BX, BY)))
    A = (BX + BUF_A[0], BY + BUF_A[1])
    Y = (BX + BUF_Y[0], BY + BUF_Y[1])
    vg = (BX + BUF_VGND[0], BY + BUF_VGND[1])
    vd = (BX + BUF_VDPWR[0], BY + BUF_VDPWR[1])
    ua0 = next(r for (n, d, r) in pins if n == "ua[0]")
    ua0_cx = (ua0[0] + ua0[2]) / 2
    ox, oy = osc_xy

    # OSC -> A: down beside the ring, over the TOP of the buffer, then down into A (A and Y are at
    # the same y, so approach A from above to avoid crossing the Y output).
    _wire(top, [(ox, oy), (ox, BY + 13.0), (A[0], BY + 13.0), A], w=0.4, layer=M4)
    _via(top, *A, [M2, M3, M4])      # A already has a Metal2 pad; just via M2->M4
    # Y -> ua[0]: out the bottom of the buffer, across to the ua[0] pin
    _wire(top, [Y, (Y[0], BY - 12.0), (ua0_cx, BY - 12.0), (ua0_cx, 0.5)], w=0.4, layer=M4)
    # power: M3 straps along the clear bottom edge to the left stripes (pads are Metal3)
    VGND_X, VDPWR_X = VGND_SX + STRIPE_W / 2, VDPWR_SX + STRIPE_W / 2
    _wire(top, [vg, (VGND_X, vg[1])], w=1.0, layer=M3); via_m4_m3(top, VGND_X, vg[1])
    _wire(top, [vd, (VDPWR_X, vd[1])], w=1.0, layer=M3); via_m4_m3(top, VDPWR_X, vd[1])


def tie_unused_low(top, pins, H):
    """Drive every unused OUTPUT pin low. uo_out[0..7] are the divider taps (used); the unused
    outputs are uio_out[0..7] and the output-enables uio_oe[0..7]. They sit contiguously on the
    top edge (x ~ 33..142), so a Metal4 rail just below the pin row taps all 16 and ties them to
    the VGND stripe. Grounding the output-enables low also keeps the bidirectional pads in input
    (high-Z) mode."""
    pr = {n: r for (n, d, r) in pins}
    targets = [f"uio_out[{i}]" for i in range(8)] + [f"uio_oe[{i}]" for i in range(8)]
    xs = sorted((pr[t][0] + pr[t][2]) / 2 for t in targets)
    y_pin = pr[targets[0]][1]                      # pin bottom (~324.4)
    yr = 323.0                                     # rail: below the pins, above the divider routing
    VGND_X = VGND_SX + STRIPE_W / 2
    # Metal4 rail across the pins, on to the VGND stripe. The stripes end at y=H-5 (< yr), so the
    # rail passes safely over the VDPWR stripe; drop a short stub into the VGND stripe to connect.
    _wire(top, [(xs[-1] + 1.0, yr), (VGND_X, yr)], w=0.5, layer=M4)
    _wire(top, [(VGND_X, yr), (VGND_X, H - 7.0)], w=0.6, layer=M4)
    # tap each unused-output pin down to the rail
    for x in xs:
        _wire(top, [(x, y_pin), (x, yr)], w=0.4, layer=M4)


def add_divider(lib, top, pins, cx, cy, H, osc_xy):
    """Place the N-stage /2../256 std-cell ripple divider in the top strip and wire it up.

    The row is built /2-leftmost but placed MIRRORED, so /2 ends up rightmost (next to uo_out[0])
    and /256 leftmost. Mapping is LSB-first: stage j (DIV2^(j+1)) -> uo_out[j] (uo_out[0]=/2 ..
    uo_out[N-1]=/256). The stage order now matches the pin order, so the output routes DON'T cross,
    and CLK lands on the right next to ua[0] (short clock route). M3 = horizontal tracks (unique
    y), M4 = vertical risers (unique x).
    """
    pdk_root = os.environ.get("PDK_ROOT", "")
    divcell, dp, std_cells = BD.build_divider(BD.STD_GDS_DEFAULT, pdk_root)
    lib.add(divcell, *std_cells)
    W = dp["_width"]; N = dp["_nstages"]
    DX0, DY0 = round(cx - W / 2, 2), 300.0      # centred under the uo_out pins
    top.add(gdstk.Reference(divcell, (DX0 + W, DY0), rotation=math.pi, x_reflection=True))

    def P(name):
        v = dp[name]; return (DX0 + W - v[0], DY0 + v[1])   # mirror: x flips, y unchanged
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
    # inter-cell filltie columns (clear of the DFF Q risers), mirrored; tap the two LEFTMOST ones
    # so the straps to the left-edge stripes stay short.
    ties = [DX0 + W - (BD.CAP_W + BD.DFF_W + BD.TIE_W + BD.INV_W + BD.TIE_W / 2
            + j * (BD.DFF_W + 2 * BD.TIE_W + BD.INV_W)) for j in range(N)]

    # --- power: VSS rail -> VGND stripe, VDD rail -> VDPWR stripe (both on the left edge). Tap VDD
    # at the LEFTMOST filltie (ties[-1]) so its M3 strap (run at the row's TOP rail, y=rail_vdd) sits
    # to the left of every divider-output flop -- otherwise it lies under the /256 flop riser and
    # forces that riser onto M4. VSS taps the next column; its strap runs at y=rail_vss=300, BELOW
    # the flop risers (which start at the Q row, y~303), so it is never in their way. ---
    vss_tap, vdd_tap = ties[-2], ties[-1]
    beefy(vss_tap, rail_vss, [M1, M2, M3])
    _wire(top, [(vss_tap, rail_vss), (VGND_X, rail_vss)], w=PW, layer=M3)
    beefy(VGND_X, rail_vss, [M3, M4])
    beefy(vdd_tap, rail_vdd, [M1, M2, M3])
    _wire(top, [(vdd_tap, rail_vdd), (VDPWR_X, rail_vdd)], w=PW, layer=M3)
    beefy(VDPWR_X, rail_vdd, [M3, M4])

    # track plan: N output tracks above the row (their order is solved below so flop risers don't
    # cross); clock and reset share the clear channel BELOW the row (between the row at y=300 and the
    # ring top at ~293) — both CLK and RN sit just below the row
    t_clk = DY0 - 3.0                                    # 297 (channel below the row, next to CLK)
    t_rn = DY0 - 5.0                                     # 295 (same channel, clear of t_clk)

    # --- clock: ua[0] (buffered OSC) up the FREE right edge straight to CLK. The mirror put CLK on
    #     the rightmost stage (just below the row, next to ua[0]), so the riser jogs across in the
    #     bottom channel and lands directly -- no excursion above the row. ---
    ua0r = next(r for (n, d, r) in pins if n == "ua[0]")
    tapx = (ua0r[0] + ua0r[2]) / 2
    ck = P("CLK")
    _wire(top, [(tapx, 0.5), (tapx, t_clk)], w=0.4, layer=M4)
    mvia(tapx, t_clk); _wire(top, [(tapx, t_clk), (ck[0], t_clk)], w=0.4, layer=M3)
    # CLK is only ~1um above the track in the clear channel — finish the short hop on M3, no M4 bounce
    _wire(top, [(ck[0], t_clk), (ck[0], ck[1])], w=0.4, layer=M3)
    _via(top, ck[0], ck[1], [M2, M3])

    # --- reset: rst_n pin -> RN, in the channel BELOW the row (clear of the outputs) ---
    rn = P("RN"); rx = pin_cx("rst_n")
    _wire(top, [(rx, pinrect["rst_n"][1]), (rx, t_rn)], w=0.4, layer=M4); mvia(rx, t_rn)
    _wire(top, [(rx, t_rn), (rn[0], t_rn)], w=0.4, layer=M3)
    # RN is just above the track in the clear channel — finish on M3, no M4 bounce
    _wire(top, [(rn[0], t_rn), (rn[0], rn[1])], w=0.4, layer=M3)
    _via(top, rn[0], rn[1], [M2, M3])

    # --- N outputs: stage j (DIV2^(j+1)) -> uo_out[j] (uo_out[0]=/2 .. uo_out[7]=/256). Each route
    # is Q -> riser -> M3 jog (at its own track) -> M4 pin-riser -> pin. The jog MUST be M3 (it
    # crosses other outputs' M4 pin-risers, and the pins are M4); the PIN-side riser MUST be M4 (it
    # climbs past higher M3 jogs). The FLOP-side riser we want on M3 — going up to M4 only to drop
    # straight back to M3 for the jog is a wasted hop. It can stay on M3 as long as its short climb
    # clears every lower jog. Whether it does is purely a question of TRACK ORDER: if flop a sits
    # under jog b, b's track must be above a's, so a's riser stops before reaching b. Those "a under
    # b" relations form a DAG for this fan, so a topological sort gives an order with ZERO flop-riser
    # crossings — every flop riser stays on M3. (flop_needs_m4 remains as a safety net: a cycle, or
    # the vdd strap, would fall back to M4 rather than short.) ---
    qxs = {j: P(f"DIV{2 ** (j + 1)}")[0] for j in range(N)}
    txs = {j: pin_cx(f"uo_out[{j}]") for j in range(N)}
    span = {j: (min(qxs[j], txs[j]), max(qxs[j], txs[j])) for j in range(N)}
    m = 0.5                                                      # clearance margin

    # order the tracks bottom->top so no flop riser crosses a lower output's jog
    under = {a: [b for b in range(N) if b != a and span[b][0] - m <= qxs[a] <= span[b][1] + m]
             for a in range(N)}                                 # b's jog covers a's flop -> b above a
    indeg = {b: sum(b in under[a] for a in range(N)) for b in range(N)}
    ready = sorted(j for j in range(N) if indeg[j] == 0)
    order = []
    while ready:
        n = ready.pop(0); order.append(n)
        for b in under[n]:
            indeg[b] -= 1
            if indeg[b] == 0:
                ready = sorted(ready + [b])
    order += [j for j in range(N) if j not in order]            # cycle remnants (none for this fan)
    t_out = {out: DY0 + 6.0 + 2.0 * i for i, out in enumerate(order)}

    vdd_strap = (min(VDPWR_X, vdd_tap), max(VDPWR_X, vdd_tap))   # M3 strap at rail_vdd
    def flop_needs_m4(j):
        """True only if the flop riser at qxs[j] (303 -> t_out[j]) still meets M3: the vdd strap, or
        a lower jog the track order couldn't lift clear (would only happen on a constraint cycle)."""
        if vdd_strap[0] - m <= qxs[j] <= vdd_strap[1] + m:
            return True
        return any(t_out[k] < t_out[j] and span[k][0] - m <= qxs[j] <= span[k][1] + m
                   for k in range(N) if k != j)

    for j in range(N):
        qx, qy = P(f"DIV{2 ** (j + 1)}")
        pin = f"uo_out[{j}]"
        tx, trk = pin_cx(pin), t_out[j]
        if flop_needs_m4(j):
            _via(top, qx, qy, [M2, M3, M4]); _wire(top, [(qx, qy), (qx, trk)], w=0.4, layer=M4)
            mvia(qx, trk)                                        # drop back to M3 for the jog
        else:
            _via(top, qx, qy, [M2, M3]); _wire(top, [(qx, qy), (qx, trk)], w=0.4, layer=M3)
        _wire(top, [(qx, trk), (tx, trk)], w=0.4, layer=M3)     # M3 jog to the pin's x
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

    # --- analog output ua[0] = osc_out: the ring OSC node drives a SkullFET inverter BUFFER
    # whose output feeds ua[0] (and, via the ua[0] pin, the divider clock). The buffer isolates
    # the ring from any external load on ua[0] -- a few pF directly on the OSC node otherwise drops
    # the ring frequency 25-60% (see DESIGN.md). The ring only sees the buffer's gate.
    osc_xy = None
    for lb in ring.labels:
        if lb.text == "OSC":
            osc_xy = (lb.origin[0] + cx, lb.origin[1] + cy)
    if osc_xy:
        add_ua_buffer(lib, top, pins, osc_xy)

    # === osc_out + 8-bit /2../256 divider (uo_out[0..7]) ===
    if osc_xy:
        add_divider(lib, top, pins, cx, cy, H, osc_xy)

    # tie unused output pins (uio_out[0..7], uio_oe[0..7]) low
    tie_unused_low(top, pins, H)

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
