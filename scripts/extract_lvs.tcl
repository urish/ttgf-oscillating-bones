# Magic LVS extraction: device-level netlist (no parasitics) for netgen LVS.
# Usage: magic ... extract_lvs.tcl <in.gds> <out.spice> <top_cell>
set input_file  [lindex $argv [expr {$argc-3}]]
set output_file [lindex $argv [expr {$argc-2}]]
set top_module  [lindex $argv [expr {$argc-1}]]
gds readonly true
gds read $input_file
load $top_module
select top cell
extract all
ext2spice lvs
ext2spice -o $output_file
quit -noprompt
