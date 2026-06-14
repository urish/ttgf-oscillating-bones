# SPDX-License-Identifier: Apache-2.0
# Author: Uri Shaked

MACRO := tt_um_oscillating_bones
# The committed gf180 skull-ring artwork. It was produced one-time by remapping the original IHP
# sg13g2 layout (see `make remap` + DESIGN.md); the IHP source GDS has been removed now that the
# migration is complete, so ring_gf180.gds is the canonical source the build starts from.
RING_GDS   := gds/ring_gf180.gds
TARGET_GDS := gds/$(MACRO).gds
TARGET_LEF := lef/$(MACRO).lef
SPICE      := spice/$(MACRO).spice
DEF        := def/tt_analog_1x2.def

PDK := gf180mcuD
MAGIC_RC := $(PDK_ROOT)/$(PDK)/libs.tech/magic/$(PDK).magicrc
DRC_DECK := $(PDK_ROOT)/$(PDK)/libs.tech/klayout/tech/drc/gf180mcu.drc

all: $(TARGET_GDS) $(TARGET_LEF)
.PHONY: all

# Assemble the full macro (GDS + LEF) from the committed gf180 ring: DEF frame + pins + power
# stripes + placed ring + std-cell /2/4/8 divider.
$(TARGET_GDS) $(TARGET_LEF): $(RING_GDS) gds/skull_buffer.gds scripts/build_gf180_macro.py scripts/build_divider.py $(DEF)
	python3 scripts/build_gf180_macro.py $(RING_GDS) $(DEF) $(TARGET_GDS)

# One-time IHP->gf180 migration that produced $(RING_GDS) (3.3V devices, 1.45x scale, implants/
# n-well taps regenerated from the original p-select). The IHP source GDS is no longer in the repo;
# supply one to regenerate the ring:  make remap IHP_SRC=path/to/ihp_source.gds
remap:
	@test -n "$(IHP_SRC)" || { echo "set IHP_SRC=path/to/ihp_source.gds"; exit 1; }
	python3 scripts/remap_to_gf180.py $(IHP_SRC) $(RING_GDS) ring 1.45
.PHONY: remap

# Extract a device-level SPICE netlist (for the manual spice/testbench.spice template).
# `make sim` and `make lvs` do their own extraction (scripts/extract_sim.tcl / extract_lvs.tcl).
$(SPICE): $(TARGET_GDS)
	magic -rcfile $(MAGIC_RC) -noconsole -dnull scripts/extract_sim.tcl $< $@ $(MACRO)

# gf180 device models + corner setup for ngspice (used by spice/testbench.spice).
spice/pdk_lib.spice:
	echo ".include $(PDK_ROOT)/$(PDK)/libs.tech/ngspice/design.ngspice" > $@
	echo ".lib $(PDK_ROOT)/$(PDK)/libs.tech/ngspice/sm141064.ngspice typical" >> $@

# Post-layout simulation: extract + ngspice, report the oscillation frequency on ua[0].
sim: $(TARGET_GDS)
	bash scripts/sim_ring.sh
.PHONY: sim

# Post-layout waveform plot for the datasheet (osc_out + /2 /4 /8 taps).
docs/layout_sim.png plot: $(TARGET_GDS)
	bash scripts/sim_plot.sh
.PHONY: plot

# Netgen LVS: layout (magic extraction) vs the intended structural source netlist.
lvs: $(TARGET_GDS)
	bash scripts/run_lvs.sh
.PHONY: lvs

# Magic sign-off DRC (matches one of the TT precheck steps).
drc: $(TARGET_GDS)
	echo "gds read $<; load $(MACRO); select top cell; drc euclidean on; drc check; drc catchup; \
		puts \"DRC violations: [drc list count total]\"" | \
		magic -rcfile $(MAGIC_RC) -noconsole -dnull
.PHONY: drc

# Full KLayout FEOL/BEOL/connectivity sign-off DRC (the authoritative gf180 deck — catches
# off-grid / exact-cut / slotting that magic DRC does not). Report goes to the (gitignored) drc/
# dir. Needs the klayout BINARY (not the python module); locally it is provided via nix-portable
# (see ~/bin/klayout, mirroring the magic wrapper). 0 real violations; the only hits are the
# die-level density rules (PL.8/M1-5.4/MT.3) satisfied by dummy fill at chip integration.
drc_klayout: $(TARGET_GDS)
	mkdir -p drc
	klayout -b -zz -r $(DRC_DECK) -rd input=$(PWD)/$< -rd report=$(PWD)/drc/gf180_drc.lyrdb \
		-rd feol=True -rd beol=True -rd conn_drc=True -rd wedge=True -rd run_mode=deep -rd thr=16 \
		-rd topcell=$(MACRO)
.PHONY: drc_klayout

clean:
	rm -f $(TARGET_GDS) $(SPICE)    # NOT $(RING_GDS) — it is committed source artwork now
.PHONY: clean
