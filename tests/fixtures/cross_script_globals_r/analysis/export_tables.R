library(readr)

df <- read_csv(file.path(ROOT_DIR, "estimates.csv"))
write_csv(df, file.path(OUTPUT_DIR, "estimates_table.csv"))
