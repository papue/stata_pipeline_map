library(readr)
df <- read_csv("intermediate/transformed.csv")
write_csv(df, "output/final_results.csv")
