* Test file for Stata table/output commands NOT currently in the parser
* Each command is a known Stata pattern that researchers commonly use

* 1. estout
estout m1 m2 using "tables/reg_main.tex", replace cells(b se) style(tex)

* 2. esttab
esttab using "tables/summary.csv", replace

* 3. outreg2
outreg2 using "tables/appendix.doc", replace word

* 4. putexcel
putexcel set "output/panel_stats.xlsx", sheet("Stats") replace

* 5. putdocx
putdocx save "reports/analysis_report.docx", replace

* 6. file open
file open fh using "logs/run_log.txt", write replace

* 7. graph save (not graph export)
graph save "figs/model_fit.gph"

* 8. outsheet
outsheet var1 var2 using "out.csv", comma replace

* 9. insheet
insheet using "data/raw_input.csv"

* 10. log using
log using "logs/session.txt", replace

* 11. copy
copy "raw/data.csv" "processed/data.csv", replace

* 12. frame save
frame save "temp/frame_data.dta"

* 13. frame load (read command)
frame load "temp/frame_data.dta"

* 14. joinby (read command)
joinby using "data/merge_key.dta"

* 15. cap save (prefix + save)
cap save "output/robust.dta"

* 16. qui save (prefix + save)
qui save "output/quiet.dta"

* 17. noi save (prefix + save)
noi save "output/noisy.dta"
