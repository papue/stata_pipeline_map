* Uses globals defined in master.do
use "${ddir}/survey.dta", clear
keep if year >= 2010
save "${pdir}/survey_clean.dta", replace
