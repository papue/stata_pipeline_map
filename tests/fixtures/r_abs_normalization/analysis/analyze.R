script_dir <- dirname(sys.frame(1)$ofile)
data_path <- file.path(script_dir, "..", "results", "all_results.csv")
df <- read.csv(data_path)
