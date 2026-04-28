use "${pdir}/survey_clean.dta", clear
reg y x1 x2
esttab using "${pdir}/tables/baseline_regs.tex", replace
