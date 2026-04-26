library(readr)
script_dir <- dirname(sys.frame(1)$ofile)
out_path <- file.path(script_dir, "..", "output", "data.csv")
write_csv(df, out_path)
