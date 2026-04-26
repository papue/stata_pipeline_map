library(writexl)
script_dir <- dirname(sys.frame(1)$ofile)
xlsx_path <- file.path(script_dir, "..", "output", "report.xlsx")
writexl::write_xlsx(df, path = xlsx_path)
