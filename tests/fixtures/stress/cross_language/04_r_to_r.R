library(readr)
df <- read_csv("output/final_results.csv")
saveRDS(df, "output/model.rds")
