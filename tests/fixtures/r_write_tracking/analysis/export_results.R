script_dir <- dirname(sys.frame(1)$ofile)
out_path <- file.path(script_dir, "..", "output", "results.csv")
write.csv(df, out_path, row.names = FALSE)
