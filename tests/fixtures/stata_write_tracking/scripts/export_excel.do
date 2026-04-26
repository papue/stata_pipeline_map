global tables "../tables"
use "data/results.dta", clear
export excel using "${tables}/table1.xlsx", replace
