script_dir <- dirname(sys.frame(1)$ofile)
plot_path <- file.path(script_dir, "plots", "distribution.png")
p <- ggplot(df, aes(x)) + geom_histogram()
ggsave(filename = plot_path, plot = p, dpi = 300)
