* Uses $datadir (which itself depends on $proj)
global rawdir "${datadir}/raw"
use "${rawdir}/survey.dta", clear
save "${datadir}/clean/survey_clean.dta", replace
