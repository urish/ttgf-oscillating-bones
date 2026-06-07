# Extract a device-level SPICE netlist (no extresist) for functional simulation.
# Usage: magic ... extract_sim.tcl <in.gds> <out.spice> <top_cell>
set input_file  [lindex $argv [expr {$argc-3}]]
set output_file [lindex $argv [expr {$argc-2}]]
set top_module  [lindex $argv [expr {$argc-1}]]
gds readonly true
gds read $input_file
load $top_module
flatten tt_um_flat
load tt_um_flat
select top cell
cellname delete $top_module
cellname rename tt_um_flat ${top_module}
extract all
ext2spice lvs
ext2spice cthresh 0.1
ext2spice -o $output_file
quit -noprompt
