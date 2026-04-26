*************************************
* 1. Load raw data
*************************************
use "data/raw.dta", clear

* 1.1 Drop missing values
drop if missing(income)

* NOTE: this is just a note, not a section header

// 2. Save cleaned
save "data/clean.dta", replace
