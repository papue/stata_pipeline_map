library(ggplot2)
library(readr)

# ROOT_DIR and OUTPUT_DIR defined in run_analysis.R
df <- read_csv(file.path(ROOT_DIR, "estimates.csv"))
p  <- ggplot(df, aes(x, y)) + geom_point()
ggsave(file.path(OUTPUT_DIR, "estimates_plot.png"), plot = p)
