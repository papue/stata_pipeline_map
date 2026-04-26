library(fs)
script_dir <- dirname(sys.frame(1)$ofile)
out_path <- fs::path(script_dir, "plots", "fs_chart.png")
ggsave(out_path)
