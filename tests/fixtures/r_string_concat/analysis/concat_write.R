script_dir <- dirname(sys.frame(1)$ofile)
base <- file.path(script_dir, "..", "output")
out_path <- paste0(base, "/summary.csv")
write.csv(df, out_path, row.names = FALSE)
