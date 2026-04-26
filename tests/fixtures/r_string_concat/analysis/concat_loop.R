script_dir <- dirname(sys.frame(1)$ofile)
for (treatment in treatments) {
    out_path <- paste0(file.path(script_dir, "plots"), "/plot_", treatment, ".png")
    ggsave(out_path)
}
