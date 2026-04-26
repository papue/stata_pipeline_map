script_dir <- dirname(sys.frame(1)$ofile)
out_file <- file.path(script_dir, "..", "output", "report.txt")

# writeLines with con= keyword
writeLines(c("line1", "line2"), con = out_file)

# cat with file= keyword
cat("text", file = file.path(script_dir, "plots", "log.txt"))

# svg() device with filename= keyword
svg(filename = file.path(script_dir, "plots", "device.svg"))
plot(1:10, 1:10)
dev.off()

# here::here() as path builder
library(here)
out <- here("output", "chart.png")
ggsave(out)
