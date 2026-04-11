global root "."
global input "$root/01_data/01_input"
global data_scripts "$root/01_data/02_scripts"
global cleaned "$root/01_data/03_cleaned_data"
global analysis_scripts "$root/02_analysis/02_scripts"
global output "$root/02_analysis/03_outputs"

use "$cleaned/panel_base.dta", clear
merge m:1 region_id using "$input/region_lookup.dta", nogen
save "$cleaned/panel_enriched.dta", replace
