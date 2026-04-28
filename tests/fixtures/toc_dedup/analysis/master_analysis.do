* ====================================================
* Table of contents
* 1. Load and clean data
* 2. Run regressions
* 3. Export tables
* ====================================================

use "data/input.dta", clear

* 1. Load and clean data
drop if missing(y)

* 2. Run regressions
reg y x1 x2

* 3. Export tables
esttab using "results/regs.tex", replace
