script_dir <- dirname(sys.frame(1)$ofile)

plot_results <- function(data, filename = NULL) {
    p <- ggplot(data, aes(x, y)) + geom_point()
    if (!is.null(filename)) {
        ggsave(filename = filename, plot = p, dpi = 300)
    }
}

# Fully resolvable at the call site:
plot_results(df, filename = file.path(script_dir, "plots", "results_a.png"))
plot_results(df, filename = file.path(script_dir, "plots", "results_b.png"))
plot_results(df, filename = file.path(script_dir, "plots", "results_c.png"))
