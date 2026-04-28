df <- read_csv(file.path(STAGE_DIR, "input.csv"))
write_csv(df, file.path(STAGE_DIR, "output.csv"))
