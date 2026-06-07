#!/usr/bin/env python3
"""
Build a /2 /4 /8 ripple frequency divider from gf180mcu_fd_sc_mcu7t5v0 standard cells.

gf180 DFFs have no QN output, so each divide-by-2 stage is a DFF (dffrnq_1: CLK, D, RN, Q)
plus an inverter (inv_2: I, ZN) wired as a toggle flip-flop (D = ~Q).  Three stages sit in an
abutted row; Q of each stage clocks the next and is also a divider output.

Power/wells: the cells are abutted into a continuous row with **filltie** cells between every
cell and **endcap** cells at the ends.  filltie/endcap tie Nwell->VDD and Pwell->VSS internally
(the std cells themselves expose VNW/VPW only as well layers, so without these taps the wells
float and the cells don't work).  The whole row shares one VDD rail (top) and one VSS rail
(bottom); the macro connects those once.

Pins are Metal1; we via up to Metal2 and route in channels above/below the row.

Returned: (cell "freq_divider", pins dict, [dff, inv, filltie, endcap]).  Pin dict is in
cell-local coords (origin at the row's lower-left): CLK, RN, DIV2, DIV4, DIV8, VDD-rect,
VSS-rect, _width.
"""
import gdstk

STD_GDS_DEFAULT = (
    "{PDK_ROOT}/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/gds/"
    "gf180mcu_fd_sc_mcu7t5v0.gds")
PREFIX = "gf180mcu_fd_sc_mcu7t5v0__"

M1, M2, VIA1 = (34, 0), (36, 0), (35, 0)
DFF_W, INV_W, TIE_W, CAP_W, H = 19.04, 3.36, 1.12, 1.12, 3.92


def _via(div, x, y):
    s = 0.13
    for lay in (M1, M2):
        div.add(gdstk.rectangle((x - 0.2, y - 0.2), (x + 0.2, y + 0.2), layer=lay[0], datatype=lay[1]))
    div.add(gdstk.rectangle((x - s, y - s), (x + s, y + s), layer=VIA1[0], datatype=VIA1[1]))


def _w(div, pts, w=0.3):
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        xa, xb = sorted((x0, x1)); ya, yb = sorted((y0, y1))
        div.add(gdstk.rectangle((xa - w / 2, ya - w / 2), (xb + w / 2, yb + w / 2),
                                layer=M2[0], datatype=M2[1]))


def build_divider(std_gds, pdk_root):
    src = gdstk.read_gds(std_gds.format(PDK_ROOT=pdk_root))
    cells = {c.name: c for c in src.cells}
    dff = cells[PREFIX + "dffrnq_1"]
    inv = cells[PREFIX + "inv_2"]
    tie = cells[PREFIX + "filltie"]
    cap = cells[PREFIX + "endcap"]

    div = gdstk.Cell("freq_divider")
    pins = {}
    FB = H + 1.4
    CK = -1.8
    RNc = -3.1

    # abutted: endcap | (dff filltie inv filltie) x3 | endcap  -> continuous rails + well taps
    x = 0.0
    div.add(gdstk.Reference(cap, (x, 0))); x += CAP_W
    placed = []
    for i in range(3):
        dffx = x; x += DFF_W
        div.add(gdstk.Reference(tie, (x, 0))); x += TIE_W
        invx = x; x += INV_W
        div.add(gdstk.Reference(tie, (x, 0))); x += TIE_W
        div.add(gdstk.Reference(dff, (dffx, 0)))
        div.add(gdstk.Reference(inv, (invx, 0)))
        placed.append((dffx, invx))
    div.add(gdstk.Reference(cap, (x, 0))); x += CAP_W
    width = x

    prev_q = None
    rn_x0 = None
    for i, (dffx, invx) in enumerate(placed):
        Q = (dffx + 18.69, 0.95)
        Qout = (dffx + 18.69, 3.0)
        D = (dffx + 3.65, 1.88)
        CLK = (dffx + 0.92, 1.96)
        RN = (dffx + 15.00, 1.30)
        Ii = (invx + 1.20, 1.91)        # inv_2 I pin
        ZN = (invx + 1.44, 3.00)        # inv_2 ZN pin
        for p in (Q, Qout, D, CLK, RN, Ii, ZN):
            _via(div, *p)

        # toggle feedback: Q -> inv.I (below), inv.ZN -> D (top channel)
        _w(div, [Q, (Q[0], CK + 0.8), (Ii[0], CK + 0.8), Ii])
        _w(div, [ZN, (ZN[0], FB), (D[0], FB), D])

        # reset rail (common), bottom-most channel
        _via(div, RN[0], RNc)
        _w(div, [RN, (RN[0], RNc)])
        if rn_x0 is None:
            pins["RN"] = (RN[0], RNc); rn_x0 = RN[0]
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
    return div, pins, [dff, inv, tie, cap]
