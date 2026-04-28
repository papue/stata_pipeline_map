* stage1 defines its own globals using parent's global
global stagedir "${rootdir}/stage1"
do "pipeline/stage1_sub.do"
