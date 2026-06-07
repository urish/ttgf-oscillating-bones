#!/usr/bin/env python3
"""
Build a /2 /4 /8 ripple frequency divider from gf180mcu_fd_sc_mcu7t5v0 standard cells.

gf180 DFFs have no QN output, so each divide-by-2 stage is a DFF (dffrnq_1: CLK, D, RN, Q)
plus an inverter (inv_1: I, ZN) wired as a toggle flip-flop (D = ~Q).  Three stages sit in a
row; Q of each stage clocks the next and is also a divider output.

The cells are spaced apart (not abutted) so the hand-routing vias/wires have clearance; the
Metal1 VDD/VSS power rails are bridged across the gaps.  Pins are Metal1; we via up to Metal2
and route in channels above/below the row.

Returned: (cell "freq_divider", pins dict, [std cells used]).  Pin dict is in cell-local
coords (origin at the row's lower-left): CLK, RN, DIV2, DIV4, DIV8, VDD-rect, VSS-rect, _width.
"""
import gdstk

STD_GDS_DEFAULT = (
    "{PDK_ROOT}/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/gds/"
    "gf180mcu_fd_sc_mcu7t5v0.gds")
PREFIX = "gf180mcu_fd_sc_mcu7t5v0__"

M1, M2, VIA1 = (34, 0), (36, 0), (35, 0)
# inv_2 has roomy, well-separated I/ZN pins (inv_1's are too tight to via cleanly)
DFF_W, INV_W, H = 19.04, 3.36, 3.92
GAP = 3.2                                  # space between cells for routing clearance


def _via(cell, x, y):
    """Via1 + Metal1/Metal2 landing pads (0.40 sq, encloses the 0.26 cut by 0.07)."""
    s = 0.13
    for lay in (M1, M2):
        cell.add(gdstk.rectangle((x - 0.2, y - 0.2), (x + 0.2, y + 0.2), layer=lay[0], datatype=lay[1]))
    cell.add(gdstk.rectangle((x - s, y - s), (x + s, y + s), layer=VIA1[0], datatype=VIA1[1]))


def _w(cell, pts, w=0.3, layer=M2):
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        xa, xb = sorted((x0, x1)); ya, yb = sorted((y0, y1))
        cell.add(gdstk.rectangle((xa - w / 2, ya - w / 2), (xb + w / 2, yb + w / 2),
                                 layer=layer[0], datatype=layer[1]))


def build_divider(std_gds, pdk_root):
    src = gdstk.read_gds(std_gds.format(PDK_ROOT=pdk_root))
    cells = {c.name: c for c in src.cells}
    dff = cells[PREFIX + "dffrnq_1"]
    inv = cells[PREFIX + "inv_2"]

    div = gdstk.Cell("freq_divider")
    pins = {}
    FB = H + 1.4           # feedback channel (above row)
    CK = -1.8              # clock-chain channel (below)
    RNc = -3.1             # reset rail channel (below clock)

    # place cells with gaps; track each cell's x-origin and the gaps between cells
    x = 0.0
    placed = []            # (dff_x, inv_x) per stage
    gaps = []              # (x_start, x_end) of each inter-cell gap
    for i in range(3):
        dffx = x
        if i > 0:
            gaps.append((x - GAP, x))          # gap before this DFF
        invx = x + DFF_W + GAP
        gaps.append((x + DFF_W, invx))         # gap between DFF and its inverter
        div.add(gdstk.Reference(dff, (dffx, 0)))
        div.add(gdstk.Reference(inv, (invx, 0)))
        placed.append((dffx, invx))
        x = invx + INV_W + GAP
    width = x - GAP

    # bridge the Metal1 VDD (3.62..4.22) and VSS (-0.30..0.30) rails across each gap
    for gx0, gx1 in gaps:
        div.add(gdstk.rectangle((gx0 - 0.1, 3.62), (gx1 + 0.1, 4.22), layer=M1[0], datatype=M1[1]))
        div.add(gdstk.rectangle((gx0 - 0.1, -0.30), (gx1 + 0.1, 0.30), layer=M1[0], datatype=M1[1]))

    prev_q = None
    for i, (dffx, invx) in enumerate(placed):
        Q = (dffx + 18.69, 0.95)
        Qout = (dffx + 18.69, 3.0)
        D = (dffx + 3.65, 1.88)         # nudged right + down to clear the cell's internal M1
        CLK = (dffx + 0.92, 1.96)
        RN = (dffx + 15.00, 1.30)       # nudged left to clear the cell's internal M1
        Ii = (invx + 1.20, 1.91)        # inv_2 I pin (0.63..2.15 x 1.705..2.12)
        ZN = (invx + 1.44, 3.00)        # inv_2 ZN pin (1.22..1.67 x 2.68..3.39)
        for p in (Q, Qout, D, CLK, RN, Ii, ZN):
            _via(div, *p)

        # toggle feedback: Q -> inv.I (in the gap to the right of the DFF), inv.ZN -> D (top)
        _w(div, [Q, (Q[0], CK + 0.8), (Ii[0], CK + 0.8), Ii])
        _w(div, [ZN, (ZN[0], FB), (D[0], FB), D])

        # reset rail (common to all DFFs), bottom-most channel
        _via(div, RN[0], RNc)
        _w(div, [RN, (RN[0], RNc)])
        if i == 0:
            pins["RN"] = (RN[0], RNc)
            rn_x0 = RN[0]
        _w(div, [(rn_x0, RNc), (RN[0], RNc)])

        # clock chain: previous Q -> this CLK
        if prev_q is None:
            pins["CLK"] = (CLK[0], CK)
            _w(div, [(CLK[0], CK), CLK])
        else:
            _w(div, [prev_q, (prev_q[0], CK), (CLK[0], CK), CLK])
        prev_q = Q
        pins[f"DIV{2 << i}"] = Qout

    pins["VDD"] = (0.0, H, width, H + 0.6)
    pins["VSS"] = (0.0, -0.3, width, 0.3)
    pins["_width"] = width
    return div, pins, [dff, inv]
