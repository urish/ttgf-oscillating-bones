#!/usr/bin/env python3
"""
Remap the hand-drawn SkullFET artwork from IHP sg13g2 layers to gf180mcuD.

The SkullFET inverters are *custom 3.3V analog devices* (nfet_03v3/pfet_03v3) drawn
as skulls.  We keep the skull geometry verbatim, translate the IHP layer numbers to
their gf180mcuD equivalents, regenerate the gf180 well/implant layers from the COMP +
Nwell geometry, and scale the whole thing by SCALE so the 130nm-era features clear the
180nm gf180 minimum width/spacing/cut rules.

Crucial gotcha: do NOT add Dualgate(55/0).  Dualgate makes magic extract the FETs as
6V medium-voltage devices (gate length >= 0.55/0.70um), which would force a ~2.5x blow
up.  As plain 3.3V devices the gate minimum is 0.28um and SCALE=1.45 is DRC-clean.

Usage: remap_to_gf180.py <in.gds> <out.gds> [top_cell] [scale]
"""
import sys
import gdstk

SCALE = 1.45  # min uniform scale that clears the 3.3V SkullFET width/spacing/gate rules

# gf180 manufacturing grid + FIXED cut sizes. The 1.45x scale puts geometry on a 1nm grid (not the
# 5nm grid) and turns the cut squares into the wrong size (IHP 0.16 contact -> 0.232, IHP via ->
# 0.275). gf180 requires every vertex on the 5nm grid (OFFGRID checks) and every cut an EXACT
# square: Contact 0.22 (CO.1), Via1/2/3 0.26 (V*.1). So after scaling we snap to the grid (via the
# output library precision) and rebuild every cut at its exact size centred on-grid -- the scaled
# metal/diffusion enclosure only grows, so the smaller exact cut still clears CO.3/CO.4/V*.3.
GRID = 0.005
CUT_SIZE = {(33, 0): 0.22, (35, 0): 0.26, (38, 0): 0.26, (40, 0): 0.26, (41, 0): 0.26}


def _snap(v):
    return round(v / GRID) * GRID

# IHP (layer,dt) -> gf180mcuD (layer,dt) for layers copied verbatim.
# gf180 usable routing metals are Metal1-4 only (Metal5/81 is forbidden, MetalTop
# unreachable), so the IHP 7-metal stack collapses: M1-M4 map directly and
# M5/TopMetal1/TopMetal2 fold onto Metal4 (concentric power rings keep their radii).
LMAP = {
    (1, 0):   (22, 0),    # Activ      -> COMP
    (5, 0):   (30, 0),    # GatPoly    -> Poly2
    (6, 0):   (33, 0),    # Cont       -> Contact
    (8, 0):   (34, 0),    # Metal1
    (8, 2):   (34, 10),   # Metal1.pin
    (10, 0):  (36, 0),    # Metal2
    (10, 2):  (36, 10),   # Metal2.pin
    (19, 0):  (35, 0),    # Via1
    (29, 0):  (38, 0),    # Via2
    (30, 0):  (42, 0),    # Metal3
    (30, 2):  (42, 10),   # Metal3.pin
    (31, 0):  (21, 0),    # NWell      -> Nwell
    (49, 0):  (40, 0),    # Via3
    (50, 0):  (46, 0),    # Metal4
    (50, 2):  (46, 10),   # Metal4.pin
    (66, 0):  (41, 0),    # Via4       -> (M4-M5 normally; rings collapse to M4)
    (67, 0):  (46, 0),    # Metal5     -> Metal4 (collapse)
    (125, 0): (41, 0),    # TopVia1    -> Via4
    (126, 0): (46, 0),    # TopMetal1  -> Metal4 (collapse)
    (126, 2): (46, 10),   # TopMetal1.pin -> Metal4.pin
    # text/label purposes (datatype 25 in IHP) -> gf180 label datatype 10
    (8, 25):  (34, 10),
    (10, 25): (36, 10),
    (30, 25): (42, 10),
    (50, 25): (46, 10),
    (126, 25):(46, 10),
}
# IHP layers that are dropped (regenerated implants, recognition, or decorative power-ring
# copies on the upper metals). The functional power rings live on Metal3 (30/0); the stacked
# decorative copies on Metal4/5/TopMetal1/2 would, after the 7->4 metal collapse, bridge the
# VGND and VDPWR rails together (they sit on top of both) and short the supplies, so they are
# dropped rather than collapsed.
DROP = {(14, 0), (30, 23), (160, 0), (189, 4),
        (50, 23), (67, 23), (126, 23), (134, 23)}

# gf180 device layers
COMP, NWELL, PPLUS, NPLUS, LVPWELL = (22, 0), (21, 0), (31, 0), (32, 0), (204, 0)
IMPLANT_ENC = 0.16   # Nplus/Pplus enclosure of COMP
NWELL_GROW = 0.30    # extra Nwell margin so DF.7 (nwell overlap of pdiff, 0.43) clears
IMPLANT_CLOSE = 0.16  # morph-close radius (unscaled): merge same-type implant gaps < 2*0.16*1.45 =
                      # 0.46um (>the NP.2/PP.2 0.4um min spacing) so abutting inverters' Nplus/Pplus
                      # become one region instead of leaving sub-0.4um slivers between them.


def _polys(shapes, layer, datatype):
    return [gdstk.Polygon(p.points, layer=layer, datatype=datatype) for p in shapes]


def regen_implants(comp_shapes, nwell_shapes, psd_shapes):
    """Build Pplus/Nplus/LVPWELL/grown-Nwell from COMP, the Nwell region and the original
    p-select (pSD).

    Implant polarity follows the *original pSD*, not Nwell membership: p+ where pSD was drawn,
    n+ everywhere else.  This is essential — the bare n+ COMP inside the Nwell are the **n-well
    taps** that tie each pfet body to VDPWR.  Assigning implants by Nwell membership (p+ for all
    COMP in Nwell) would bury those taps under Pplus and leave the wells floating.
    """
    comp = gdstk.boolean(comp_shapes, [], "or")
    nwell = gdstk.boolean(nwell_shapes, [], "or") if nwell_shapes else []
    psd = gdstk.boolean(psd_shapes, [], "or") if psd_shapes else []
    if psd:
        pcomp = gdstk.boolean(comp, psd, "and")
        ncomp = gdstk.boolean(comp, psd, "not")
    elif nwell:                                  # fallback: old Nwell-membership rule
        pcomp = gdstk.boolean(comp, nwell, "and")
        ncomp = gdstk.boolean(comp, nwell, "not")
    else:
        pcomp, ncomp = [], comp
    # LVPWELL belongs only under the NMOS (n+ COMP OUTSIDE the Nwell); the n+ n-well taps,
    # which sit inside the Nwell, must NOT get LVPWELL.
    nmos = gdstk.boolean(ncomp, nwell, "not") if (ncomp and nwell) else ncomp
    def _enc_close(comp_region):
        """Enclose COMP by IMPLANT_ENC, then morph-close so same-type regions closer than the
        NP.2/PP.2 min spacing merge into one (no sub-0.4um slivers)."""
        if not comp_region:
            return []
        enc = gdstk.offset(comp_region, IMPLANT_ENC, join="miter", use_union=True)
        grown = gdstk.offset(enc, IMPLANT_CLOSE, join="miter", use_union=True)
        return gdstk.offset(grown, -IMPLANT_CLOSE, join="miter", use_union=True)

    # keep each implant >=0.16um from the opposite-type diffusion (PP.3a/NP.3a): clip the closed
    # Pplus off the nfet NCOMP halo and the closed Nplus off the pfet PCOMP halo.
    pplus = _enc_close(pcomp)
    nplus = _enc_close(ncomp)
    if pplus and nmos:
        pplus = gdstk.boolean(pplus, gdstk.offset(nmos, 0.16, join="miter", use_union=True), "not")
    pmos = gdstk.boolean(pcomp, nwell, "and") if (pcomp and nwell) else pcomp
    if nplus and pmos:
        nplus = gdstk.boolean(nplus, gdstk.offset(pmos, 0.16, join="miter", use_union=True), "not")

    out = []
    for p in pplus:
        out.append(gdstk.Polygon(p.points, layer=PPLUS[0], datatype=PPLUS[1]))
    for p in nplus:
        out.append(gdstk.Polygon(p.points, layer=NPLUS[0], datatype=NPLUS[1]))
    for p in gdstk.offset(nmos, 0.45, join="miter") if nmos else []:
        out.append(gdstk.Polygon(p.points, layer=LVPWELL[0], datatype=LVPWELL[1]))
    for p in gdstk.offset(nwell, NWELL_GROW, join="miter") if nwell else []:
        out.append(gdstk.Polygon(p.points, layer=NWELL[0], datatype=NWELL[1]))
    return out


def remap_flat(in_gds, top_name, scale=SCALE):
    """Flatten `top_name`, remap layers, regenerate implants, scale. Returns a Library."""
    lib = gdstk.read_gds(in_gds)
    cell = {c.name: c for c in lib.cells}[top_name]
    flat = cell.copy("_flat", deep_copy=True).flatten()

    comp_src, nwell_src, psd_src, kept = [], [], [], []
    for p in flat.get_polygons():
        k = (p.layer, p.datatype)
        if k == (1, 0):
            comp_src.append(p)
        elif k == (31, 0):
            nwell_src.append(p)
        elif k == (14, 0):              # IHP pSD (p-select) — drives implant polarity, not mapped
            psd_src.append(p)
        if k in DROP:
            continue
        tgt = LMAP.get(k)
        if tgt is None:
            continue  # unmapped -> drop
        kept.append(gdstk.Polygon(p.points, layer=tgt[0], datatype=tgt[1]))

    implants = regen_implants(comp_src, nwell_src, psd_src)

    out = gdstk.Library(unit=1e-6, precision=GRID * 1e-6)   # write rounds every coord to the 5nm grid
    nc = out.new_cell(top_name)
    for p in kept + implants:
        p.scale(scale)
        nc.add(p)
    # Bring one inverter output up to Metal4 and label it OSC so the macro can tap the live
    # oscillation cleanly. We pick the "Y" (output) pin nearest angle 0 (the rightmost stage);
    # its node is on Metal1/Metal2, so we stack Via2/Via3 up to a Metal4 pad.
    import math as _m
    ys = [lb for lb in flat.labels if lb.text == "Y"]
    if ys:
        # nearest angle -45 deg (bottom-right), close to the ua[0] pin, away from the supply pads
        def _adist(lb):
            a = _m.degrees(_m.atan2(lb.origin[1], lb.origin[0])) % 360
            return min(abs(a - 315), 360 - abs(a - 315))
        osc = min(ys, key=_adist)
        ox, oy = osc.origin[0] * scale, osc.origin[1] * scale
        s = 0.13
        for lay in ((36, 0), (42, 0), (46, 0)):           # M2/M3/M4 landing pads
            nc.add(gdstk.rectangle((ox - 0.6, oy - 0.6), (ox + 0.6, oy + 0.6),
                                   layer=lay[0], datatype=lay[1]))
        for lay in ((38, 0), (40, 0)):                    # Via2 (M2-M3), Via3 (M3-M4)
            for dx in (-0.28, 0.28):
                for dy in (-0.28, 0.28):
                    nc.add(gdstk.rectangle((ox + dx - s, oy + dy - s), (ox + dx + s, oy + dy + s),
                                           layer=lay[0], datatype=lay[1]))
        nc.add(gdstk.Label("OSC", (ox, oy), layer=46, texttype=10))

    # Only keep GLOBAL power labels. The per-inverter A/Y pin labels are local names; once the
    # ring is flattened, keeping them would make magic merge every "A" (and every "Y") into one
    # net, collapsing the 21-stage chain into 21 parallel inverters. Inter-stage connectivity is
    # geometric (Y of stage i abuts A of stage i+1), so we drop the signal labels.
    POWER_LABELS = {"VGND", "VDPWR", "VAPWR", "VPWR", "VDD", "VSS"}
    for lb in flat.labels:
        if lb.text not in POWER_LABELS:
            continue
        tgt = LMAP.get((lb.layer, lb.texttype))
        if tgt:
            nc.add(gdstk.Label(lb.text, (lb.origin[0] * scale, lb.origin[1] * scale),
                               layer=tgt[0], texttype=tgt[1]))

    # --- gf180 sign-off geometry fix: rebuild every contact/via as an EXACT fixed-size square,
    # centred on the 5nm grid (CO.1 / V*.1 require an exact cut size; the 1.45x scale made them the
    # wrong size). Bulk geometry is snapped to grid by the library precision set above. ---
    cuts = [p for p in nc.polygons if (p.layer, p.datatype) in CUT_SIZE]
    centres = []
    for p in cuts:
        xs = p.points[:, 0]; ys = p.points[:, 1]
        w, h = xs.max() - xs.min(), ys.max() - ys.min()
        if max(w, h) > 0.40:        # guard: a real cut is a single small square, not a bar/array
            raise SystemExit(f"remap: {(p.layer, p.datatype)} cut is {w:.3f}x{h:.3f}um — "
                             "looks like a bar; would need array fill, not 1:1 replacement")
        centres.append(((p.layer, p.datatype), _snap((xs.min() + xs.max()) / 2),
                        _snap((ys.min() + ys.max()) / 2)))
    nc.remove(*cuts)
    for (lay, cx, cy) in centres:
        s = CUT_SIZE[lay] / 2
        nc.add(gdstk.rectangle((cx - s, cy - s), (cx + s, cy + s), layer=lay[0], datatype=lay[1]))
    return out


if __name__ == "__main__":
    in_gds, out_gds = sys.argv[1], sys.argv[2]
    top = sys.argv[3] if len(sys.argv) > 3 else "tt_um_oscillating_bones"
    scale = float(sys.argv[4]) if len(sys.argv) > 4 else SCALE
    lib = remap_flat(in_gds, top, scale)
    lib.write_gds(out_gds)
    c = lib.cells[0]
    bb = c.bounding_box()
    print(f"wrote {out_gds}: cell {c.name}  {bb[1][0]-bb[0][0]:.1f} x {bb[1][1]-bb[0][1]:.1f} um "
          f"(scale {scale})")
