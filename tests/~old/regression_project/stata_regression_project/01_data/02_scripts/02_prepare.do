use "./01_data/03_cleaned_data/panel_base.dta", clear
append using "archive/01_input/legacy.csv"
save "01_data/03_cleaned_data/panel_ready.dta", replace
