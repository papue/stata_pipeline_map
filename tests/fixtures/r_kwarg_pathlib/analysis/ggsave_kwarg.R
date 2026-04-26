script_dir <- dirname(sys.frame(1)$ofile)
out_file <- file.path(script_dir, "plots", "final_plot.png")
p <- ggplot(df, aes(x, y)) + geom_point()
ggsave(filename = out_file, plot = p, width = 8, height = 6)
