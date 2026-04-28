global root    "data/project"
global rawdir  "${root}/raw"
global outdir  "${root}/output"

use "${rawdir}/survey.dta", clear
save "${outdir}/survey_clean.dta", replace
