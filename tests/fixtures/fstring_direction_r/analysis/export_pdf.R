case  <- "scenario_a"
alpha <- 0.05

pdf_path <- sprintf("results/%s_alpha%.2f.pdf", case, alpha)
pdf(pdf_path, width = 8, height = 6)
plot(1:10)
dev.off()
