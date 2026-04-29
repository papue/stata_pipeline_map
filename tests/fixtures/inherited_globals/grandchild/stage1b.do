* stage1b.do — grandchild inherits $outdir from stage1 (chained global)
use "${outdir}/stage1_out.dta", clear
save "${outdir}/stage1b_out.dta", replace
