local outpath "../output"
use "data/clean.dta", clear
export delimited "`outpath'/summary.csv", replace
