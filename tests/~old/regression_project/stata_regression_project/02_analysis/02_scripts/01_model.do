use "01_data/03_cleaned_data/panel_ready.dta", clear
merge 1:1 id using "02_analysis/01_input/specs.dta"
save "02_analysis/03_outputs/model_output.dta", replace
export delimited using "02_analysis/03_outputs/results.csv", replace
