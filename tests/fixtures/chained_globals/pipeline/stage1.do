* Defines output dir using inherited $root global
global outdir "${root}/processed"
use "${root}/raw/input.dta", clear
save "${outdir}/stage1_out.dta", replace
