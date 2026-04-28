global outdir "results"
local metric  "welfare"

use "data/estimates.dta", clear
export excel "${outdir}/`metric'_table.xlsx", replace firstrow(variables)
