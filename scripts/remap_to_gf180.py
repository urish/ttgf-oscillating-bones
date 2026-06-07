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

SCALE = 1.45  # min uniform scale that is DRC-clean for the 3.3V SkullFET

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
    (50, 23): (46, 0),    # Metal4 power-ring art
    (66, 0):  (41, 0),    # Via4       -> (M4-M5 normally; rings collapse to M4)
    (67, 0):  (46, 0),    # Metal5     -> Metal4 (collapse)
    (67, 23): (46, 0),    # Metal5 power-ring art -> Metal4
    (125, 0): (41, 0),    # TopVia1    -> Via4
    (126, 0): (46, 0),    # TopMetal1  -> Metal4 (collapse)
    (126, 2): (46, 10),   # TopMetal1.pin -> Metal4.pin
    (126, 23):(46, 0),    # TopMetal1 power-ring art -> Metal4
    (134, 23):(42, 0),    # TopMetal2 power-ring art -> Metal3 (keep distinct from M4)
}
# IHP layers that are dropped (regenerated or non-fab recognition/art):
DROP = {(14, 0), (30, 23), (160, 0), (189, 4)}

# gf180 device layers
COMP, NWELL, PPLUS, NPLUS, LVPWELL = (22, 0), (21, 0), (31, 0), (32, 0), (204, 0)
IMPLANT_ENC = 0.16   # Nplus/Pplus enclosure of COMP
NWELL_GROW = 0.30    # extra Nwell margin so DF.7 (nwell overlap of pdiff, 0.43) clears


def _polys(shapes, layer, datatype):
    return [gdstk.Polygon(p.points, layer=layer, datatype=datatype) for p in shapes]


def regen_implants(comp_shapes, nwell_shapes):
    """Build Pplus/Nplus/LVPWELL/grown-Nwell from COMP and the (PMOS) Nwell region."""
    comp = gdstk.boolean(comp_shapes, [], "or")
    nwell = gdstk.boolean(nwell_shapes, [], "or") if nwell_shapes else []
    pcomp = gdstk.boolean(comp, nwell, "and") if nwell else []
    ncomp = gdstk.boolean(comp, nwell, "not") if nwell else comp
    out = []
    if pcomp:
        for p in gdstk.offset(pcomp, IMPLANT_ENC, join="miter"):
            out.append(gdstk.Polygon(p.points, layer=PPLUS[0], datatype=PPLUS[1]))
    if ncomp:
        for p in gdstk.offset(ncomp, IMPLANT_ENC, join="miter"):
            out.append(gdstk.Polygon(p.points, layer=NPLUS[0], datatype=NPLUS[1]))
        for p in gdstk.offset(ncomp, 0.45, join="miter"):
            out.append(gdstk.Polygon(p.points, layer=LVPWELL[0], datatype=LVPWELL[1]))
    if nwell:
        for p in gdstk.offset(nwell, NWELL_GROW, join="miter"):
            out.append(gdstk.Polygon(p.points, layer=NWELL[0], datatype=NWELL[1]))
    return out


def remap_flat(in_gds, top_name, scale=SCALE):
    """Flatten `top_name`, remap layers, regenerate implants, scale. Returns a Library."""
    lib = gdstk.read_gds(in_gds)
    cell = {c.name: c for c in lib.cells}[top_name]
    flat = cell.copy("_flat", deep_copy=True).flatten()

    comp_src, nwell_src, kept = [], [], []
    for p in flat.get_polygons():
        k = (p.layer, p.datatype)
        if k == (1, 0):
            comp_src.append(p)
        elif k == (31, 0):
            nwell_src.append(p)
        if k in DROP:
            continue
        tgt = LMAP.get(k)
        if tgt is None:
            continue  # unmapped -> drop
        kept.append(gdstk.Polygon(p.points, layer=tgt[0], datatype=tgt[1]))

    implants = regen_implants(comp_src, nwell_src)

    out = gdstk.Library()
    nc = out.new_cell(top_name)
    for p in kept + implants:
        p.scale(scale)
        nc.add(p)
    for lb in flat.labels:
        tgt = LMAP.get((lb.layer, lb.texttype))
        if tgt:
            nc.add(gdstk.Label(lb.text, (lb.origin[0] * scale, lb.origin[1] * scale),
                               layer=tgt[0], texttype=tgt[1]))
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
