global root "/foreign/machine/stata_regression_project"
import delimited "$root/01_data/01_input/source.csv", clear
save "$root/01_data/03_cleaned_data/panel_base.dta", replace
