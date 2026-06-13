#!/usr/bin/env python3
"""
Generate a structural *source* SPICE netlist of the intended circuit for netgen LVS:
a 21-stage ring of CMOS inverters (the SkullFETs, as nfet_03v3/pfet_03v3) whose output drives
uo_out[0]/ua[0] and a 3-stage std-cell ripple divider (dffrnq_1 + inv_2) -> uo_out[1..3].

This is the "schematic" side of LVS; the "layout" side is the magic extraction of the GDS.
Device sizes match the remapped SkullFET (W=5.87u, L=0.58u).  The std cells are referenced as
subcircuits (netgen reads their definitions from the PDK spice via the netgen setup).

Usage: gen_lvs_source.py <out.spice>
"""
import sys

N = 21          # ring stages
W, L = "5.87u", "0.58u"


def main(out):
    # full top-level pin list (must match the layout / DEF). Unused pins are declared but float.
    ports = ["VGND", "VDPWR", "clk", "ena", "rst_n"]
    for b in ("ui_in", "uio_in", "uio_out", "uio_oe", "uo_out"):
        ports += [f"{b}[{i}]" for i in range(8)]
    ports += [f"ua[{i}]" for i in range(8)]
    s = ["* Source netlist for LVS — tt_um_oscillating_bones (intended topology)",
         ".subckt tt_um_oscillating_bones " + " ".join(ports)]
    # ring: inverter i connects node n{i} -> n{i+1 mod N}
    for i in range(N):
        a, y = f"n{i}", f"n{(i + 1) % N}"
        s.append(f"Mp{i} {y} {a} VDPWR VDPWR pfet_03v3 W={W} L={L}")
        s.append(f"Mn{i} {y} {a} VGND VGND nfet_03v3 W={W} L={L}")
    osc = "n0"                                   # the tapped oscillator node
    # ua[0] output buffer: one SkullFET inverter, ring OSC -> ua[0]
    s.append(f"Mbp ua[0] {osc} VDPWR VDPWR pfet_03v3 W={W} L={L}")
    s.append(f"Mbn ua[0] {osc} VGND VGND nfet_03v3 W={W} L={L}")
    # 8-stage toggle-DFF ripple divider clocked by ua[0] (the buffered node the clock taps),
    # reset by rst_n. Stage j (/2^(j+1)) -> uo_out[j]  (LSB-first: uo_out[0]=/2 .. uo_out[7]=/256).
    prev = "ua[0]"
    for i in range(8):
        q = f"uo_out[{i}]"
        qb = f"qb{i}"
        s.append(f"Xdff{i} {prev} {qb} rst_n {q} VDPWR VGND VDPWR VGND "
                 f"gf180mcu_fd_sc_mcu7t5v0__dffrnq_1")
        s.append(f"Xinv{i} {q} {qb} VDPWR VGND VDPWR VGND gf180mcu_fd_sc_mcu7t5v0__inv_2")
        prev = q
    s.append(".ends")
    open(out, "w").write("\n".join(s) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main(sys.argv[1])
