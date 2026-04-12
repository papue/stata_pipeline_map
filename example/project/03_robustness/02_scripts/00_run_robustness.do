global root "."
global input "$root/01_data/01_input"
global data_scripts "$root/01_data/02_scripts"
global cleaned "$root/01_data/03_cleaned_data"
global analysis_scripts "$root/02_analysis/02_scripts"
global output "$root/02_analysis/03_outputs"
global robust_scripts "$root/03_robustness/02_scripts"
global robust_output "$root/03_robustness/03_outputs"


do "$robust_scripts/01_alt_sample.do"
do "$robust_scripts/02_robustness_models.do"
do "$robust_scripts/03_placebo_checks.do"
