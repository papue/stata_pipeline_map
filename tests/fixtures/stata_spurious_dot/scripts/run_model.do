* SCENARIO is passed as a command-line argument — not statically resolvable
* do run_model.do baseline
local scenario "`1'"

use "./${scenario}.dta", clear
save "./${scenario}_results.dta", replace
