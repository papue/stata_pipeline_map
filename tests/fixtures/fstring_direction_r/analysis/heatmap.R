library(ggplot2)
library(glue)

demand_label <- "high"
fig_path <- glue("plots/profit_heatmap_demand{demand_label}.png")

p <- ggplot(mtcars, aes(mpg, cyl)) + geom_point()
ggsave(fig_path, plot = p)
