library(arrow)
script_dir <- dirname(sys.frame(1)$ofile)
sink_path <- file.path(script_dir, "..", "output", "results.parquet")
write_parquet(df, sink = sink_path)
