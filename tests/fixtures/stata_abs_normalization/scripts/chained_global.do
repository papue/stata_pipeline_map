global root "C:\project_external"
global data "${root}\data"
use "${data}\analysis.dta", clear
export delimited "${data}\output.csv", replace
