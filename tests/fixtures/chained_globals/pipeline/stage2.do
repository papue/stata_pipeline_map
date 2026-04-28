* Uses $outdir defined in stage1.do -- two inherited links
use "${outdir}/stage1_out.dta", clear
save "${outdir}/stage2_final.dta", replace
