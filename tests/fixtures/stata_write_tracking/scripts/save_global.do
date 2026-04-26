global outdir "../output"
use "data/analysis.dta", clear
save "${outdir}/results.dta", replace
