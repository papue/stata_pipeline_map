args <- commandArgs(trailingOnly = TRUE)
param_file <- args[1]  # runtime — not statically resolvable

params <- jsonlite::fromJSON(paste0("./", param_file, ".json"))
