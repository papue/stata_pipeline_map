* stage2.do — inherits $root from master; redefines $root (child wins)
global root "data/override"
use "${root}/other.dta", clear
save "${root}/stage2_out.dta", replace
