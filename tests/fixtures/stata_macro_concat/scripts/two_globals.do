global root "../data"
global subdir "processed"
use "$root/$subdir/results.dta", clear
save "$root/$subdir/output.dta", replace
