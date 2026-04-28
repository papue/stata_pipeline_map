local outdir "results/tables"
local tname  "summary_stats"

use "data/input.dta", clear
save "`outdir'/`tname'.dta", replace
