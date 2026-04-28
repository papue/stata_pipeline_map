library(ggplot2)

plot_name <- "baseline"
out_dir   <- "plots"

p <- ggplot(mtcars, aes(mpg, cyl)) + geom_point()

save_path <- paste0(out_dir, "/", plot_name, ".png")
ggsave(save_path, plot = p, dpi = 300)
