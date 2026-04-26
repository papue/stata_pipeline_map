# Trigger script for MO-26: spurious "." node regression test.
# Before the fix, file.path(".") stores "." in vars_map and read.csv(path)
# emits a node with id ".".  After the fix, no node is emitted.
path <- file.path(".")
df <- read.csv(path)
