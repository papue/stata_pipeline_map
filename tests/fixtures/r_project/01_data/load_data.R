# Stage 1: Load and save raw survey data
library(readr)

DATA_DIR <- "data"

# Read raw data using readr
df <- read_csv("data/raw/survey.csv")

# Save as RDS for fast reloading
saveRDS(df, "data/clean/survey_clean.rds")

# Also write CSV for compatibility
write_csv(df, "data/clean/survey_clean.csv")
