* Define project globals
global ddir "data/raw"
global pdir "output"

do "analysis/clean.do"
do "analysis/regressions.do"
