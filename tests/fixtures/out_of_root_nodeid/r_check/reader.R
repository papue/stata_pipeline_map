script_dir <- dirname(sys.frame(1)$ofile)
df <- read.csv(file.path(script_dir, "../../absolute/path/outside/root/output.csv"))
