script_dir <- dirname(sys.frame(1)$ofile)
model_path <- file.path(script_dir, "..", "models", "fit.rds")
saveRDS(model, file = model_path)
