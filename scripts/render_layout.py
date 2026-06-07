#!/usr/bin/env python3
"""
Render a gf180mcuD GDS to PNG with skull-friendly colours (gdstk SVG -> cairosvg).
Standalone (no klayout binary needed).

Usage: render_layout.py <in.gds> <out.png> [width] [cellname]
"""
import sys
import gdstk
import cairosvg

# gf180 (layer,dt) -> (fill, stroke, fill-opacity, z-order)
STYLE = {
    (0, 0):   ("none",    "#ff3333", 0.0,  -1),   # PR_bndry
    (204, 0): ("#d2b48c", "#a0825a", 0.18,  1),   # LVPWELL
    (21, 0):  ("#f0e68c", "#bdbd5a", 0.22,  2),   # Nwell
    (31, 0):  ("#ff79c6", "#aa3070", 0.18,  3),   # Pplus
    (32, 0):  ("#8aff8a", "#30aa30", 0.18,  3),   # Nplus
    (22, 0):  ("#2e8b57", "#10331f", 0.85,  4),   # COMP
    (30, 0):  ("#d92b2b", "#7a1010", 0.70,  5),   # Poly2
    (33, 0):  ("#000000", "#000000", 0.95,  6),   # Contact
    (34, 0):  ("#3b6fe0", "#1a3a8a", 0.50,  7),   # Metal1
    (34, 10): ("#9ab8ff", "#1a3a8a", 0.85,  7),
    (35, 0):  ("#101010", "#000000", 0.95,  8),   # Via1
    (36, 0):  ("#c44ec4", "#6a1f6a", 0.42,  9),   # Metal2
    (38, 0):  ("#101010", "#000000", 0.95, 10),   # Via2
    (42, 0):  ("#e8901e", "#7a4a0f", 0.45, 11),   # Metal3
    (42, 10): ("#ffcc66", "#7a4a0f", 0.85, 11),
    (40, 0):  ("#101010", "#000000", 0.95, 11),   # Via3
    (41, 0):  ("#101010", "#000000", 0.95, 12),   # Via4
    (46, 0):  ("#13b0a5", "#0a6058", 0.55, 13),   # Metal4
    (46, 10): ("#6fe0d8", "#0a6058", 0.90, 13),
}


def render(gds, png, width=800, cellname=None, bg="#ffffff"):
    lib = gdstk.read_gds(gds)
    cell = ([c for c in lib.cells if c.name == cellname][0]
            if cellname else lib.top_level()[0])
    shape = {}
    for k, (f, s, o, _z) in STYLE.items():
        d = {"stroke": s}
        if f == "none":
            d["fill"] = "none"
            d["stroke-width"] = "0.3"
        else:
            d["fill"] = f
            d["fill-opacity"] = str(o)
        shape[k] = d
    zof = {k: v[3] for k, v in STYLE.items()}
    svg = png.rsplit(".", 1)[0] + ".svg"
    cell.write_svg(svg, scaling=2, shape_style=shape, background=bg, pad="2%",
                   sort_function=lambda a, b: zof.get((a.layer, a.datatype), 50)
                   < zof.get((b.layer, b.datatype), 50))
    cairosvg.svg2png(url=svg, write_to=png, output_width=width)
    print(f"wrote {png}")


if __name__ == "__main__":
    render(sys.argv[1], sys.argv[2],
           int(sys.argv[3]) if len(sys.argv) > 3 else 800,
           sys.argv[4] if len(sys.argv) > 4 else None)
