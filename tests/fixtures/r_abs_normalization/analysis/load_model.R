script_dir <- dirname(sys.frame(1)$ofile)
in_path <- file.path(script_dir, "..", "results", "model_output.parquet")
df <- arrow::read_parquet(in_path)
