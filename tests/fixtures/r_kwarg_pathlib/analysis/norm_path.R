script_dir <- dirname(sys.frame(1)$ofile)
raw_path <- file.path(script_dir, "plots", "output.png")
clean_path <- normalizePath(raw_path, mustWork = FALSE)
ggsave(clean_path)
