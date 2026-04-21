library(readr)
df <- read_csv("data/input.csv")
saveRDS(df, "output/model.rds")
