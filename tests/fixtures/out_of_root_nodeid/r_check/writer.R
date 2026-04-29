base_dir <- "/absolute/path/outside/root"
write.csv(df, file.path(base_dir, "output.csv"))
