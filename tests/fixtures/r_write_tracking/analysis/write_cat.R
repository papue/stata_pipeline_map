script_dir <- dirname(sys.frame(1)$ofile)
log_path <- file.path(script_dir, "..", "output", "log.txt")
cat("some output\n", file = log_path)
