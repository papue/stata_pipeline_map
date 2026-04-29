* master.do — defines globals used by children
global root "data/project"
global indir "data/raw"
do "child/stage1.do"
do "child/stage2.do"
