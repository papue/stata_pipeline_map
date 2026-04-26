script_dir <- dirname(sys.frame(1)$ofile)
for (treatment in treatments) {
    out_file <- file.path(script_dir, "plots", paste0("plot_", treatment, ".png"))
    ggsave(filename = out_file)
}
