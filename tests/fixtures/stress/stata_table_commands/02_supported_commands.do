* Test file for commands that ARE currently supported by the parser

* use (read)
use "data/input.dta", clear

* save (write)
save "output/result.dta", replace

* export delimited (write)
export delimited using "output/result.csv", replace

* export excel (write)
export excel using "output/result.xlsx", replace

* graph export (write)
graph export "figs/fig1.pdf", replace

* import delimited (read)
import delimited "data/raw.csv"

* merge (read)
merge 1:1 id using "data/other.dta"

* append (read)
append using "data/extra.dta"
