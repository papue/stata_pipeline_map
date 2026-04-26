global datadir "../data"
local variant "v2"
use "$datadir/results_`variant'.dta", clear
save "$datadir/output_`variant'.dta", replace
