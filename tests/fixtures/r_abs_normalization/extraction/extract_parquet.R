base_dir <- "C:/project_external/results"
out_path <- file.path(base_dir, "model_output.parquet")
arrow::write_parquet(df, out_path)
