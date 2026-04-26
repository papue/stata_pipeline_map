base_dir <- "../data"
suffix <- "final"
path <- sprintf("%s/results_%s.csv", base_dir, suffix)
df <- read.csv(path)
