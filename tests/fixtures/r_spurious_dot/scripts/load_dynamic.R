args <- commandArgs(trailingOnly = TRUE)
config_name <- args[1]
path <- file.path(".", config_name)
df <- read.csv(path)
