* Test script for classification
use "output/data_clean.dta", clear
export delimited using "output/results.csv", replace
graph export "output/figure.png", replace
graph export "output/report.html", replace
save "output/data_tmp.dta", replace
save "output/data_temp.dta", replace
save "output/debug_check.dta", replace

* Second script reads data_tmp so it's not internal-only
use "output/data_tmp.dta", clear
use "output/data_temp.dta", clear
use "output/debug_check.dta", clear
use "output/report.html", clear
