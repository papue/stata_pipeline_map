local outdir "results/tables"
local spec   "baseline"

use "data/estimates.dta", clear
eststo: reg y x1 x2

esttab using "`outdir'/`spec'_regs.tex", replace label
