* stage1.do — inherits $root, defines $outdir, calls grandchild
global outdir "${root}/processed"
use "${indir}/input.dta", clear
save "${outdir}/stage1_out.dta", replace
do "grandchild/stage1b.do"
