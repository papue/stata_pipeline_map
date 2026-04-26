args <- commandArgs(trailingOnly = TRUE)
wave <- args[1]  # runtime
df <- read.csv(paste0("../data/wave_", wave, ".csv"))
