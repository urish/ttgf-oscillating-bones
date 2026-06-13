#!/usr/bin/env python3
"""
Plot post-layout simulation waveforms (osc_out + divider taps) to a PNG for the datasheet.

Reads an ngspice `wrdata` file (alternating time/value columns) and stacks the traces.
Usage: plot_wave.py <wave.txt> <out.png>
"""
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

data = np.loadtxt(sys.argv[1])
out = sys.argv[2]
t = data[:, 0] * 1e9                       # seconds -> ns
mask = t >= 20.0                           # drop the reset/start-up transient

traces = [
    ("osc_out\n(ua[0], ~120 MHz)", 1, "#0a6058"),
    ("osc_div_2\n(uo_out[0])",     3, "#13b0a5"),
    ("osc_div_4\n(uo_out[1])",     5, "#e8901e"),
    ("osc_div_8\n(uo_out[2])",     7, "#c44ec4"),
]

fig, axes = plt.subplots(len(traces), 1, sharex=True, figsize=(8.5, 5.0))
for ax, (name, col, color) in zip(axes, traces):
    ax.plot(t[mask], data[mask, col], color=color, lw=1.1)
    ax.set_ylabel(name, rotation=0, ha="right", va="center", fontsize=8.5)
    ax.set_ylim(-0.4, 3.7)
    ax.set_yticks([0, 3.3])
    ax.tick_params(labelsize=8)
    ax.grid(True, axis="x", alpha=0.25)
    ax.margins(x=0)
axes[-1].set_xlabel("time (ns)")
fig.suptitle("SkullFET ring oscillator — post-layout simulation (gf180mcu)", fontsize=11)
fig.tight_layout(rect=(0.04, 0, 1, 0.96))
fig.savefig(out, dpi=120)
print(f"wrote {out}")
