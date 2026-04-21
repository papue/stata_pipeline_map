# Stage 2: Analyse survey data and produce outputs
library(ggplot2)
library(here)

# Source the data loading script
source("01_data/load_data.R")

# Read cleaned data
df <- readRDS("data/clean/survey_clean.rds")

# Build path using here()
output_path <- here("results", "income_distribution.png")

# Plot and export
p <- ggplot(df, aes(x = income)) + geom_histogram()
ggsave(output_path, plot = p, width = 8, height = 6)
ggsave(filename = "results/income_distribution_alt.pdf", plot = p)

# Export summary table
write.csv(summary(df), "results/summary_stats.csv")
