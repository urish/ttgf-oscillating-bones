# SPDX-License-Identifier: Apache-2.0
# Author: Uri Shaked

MACRO := tt_um_oscillating_bones
SOURCE_GDS := gds/$(MACRO).source.gds
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

# 1) Remap the IHP SkullFET ring artwork to gf180mcuD layers (3.3V devices, 1.45x scale).
$(RING_GDS): $(SOURCE_GDS) scripts/remap_to_gf180.py
	python3 scripts/remap_to_gf180.py $< $@ ring 1.45

# 2) Assemble the full macro (GDS + LEF): DEF frame + pins + power stripes + placed ring.
$(TARGET_GDS) $(TARGET_LEF): $(RING_GDS) scripts/build_gf180_macro.py $(DEF)
	python3 scripts/build_gf180_macro.py $(RING_GDS) $(DEF) $(TARGET_GDS)

# Extract a SPICE netlist for simulation/LVS.
$(SPICE): $(TARGET_GDS)
	magic -rcfile $(MAGIC_RC) -noconsole -dnull scripts/extract_for_sim.tcl $< $@ $(MACRO)

# Magic sign-off DRC (matches one of the TT precheck steps).
drc: $(TARGET_GDS)
	echo "gds read $<; load $(MACRO); select top cell; drc euclidean on; drc check; drc catchup; \
		puts \"DRC violations: [drc list count total]\"" | \
		magic -rcfile $(MAGIC_RC) -noconsole -dnull
.PHONY: drc

# KLayout FEOL/BEOL DRC (as run in CI precheck).
drc_klayout: $(TARGET_GDS)
	klayout -b -r $(DRC_DECK) -rd input=$(PWD)/$< -rd report=$(PWD)/drc/gf180_drc.lyrdb
.PHONY: drc_klayout

clean:
	rm -f $(TARGET_GDS) $(RING_GDS) $(SPICE)
.PHONY: clean
