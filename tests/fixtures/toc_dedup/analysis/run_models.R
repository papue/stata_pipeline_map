# Table of contents:
## 1. Load data ----
## 2. Fit models ----
## 3. Export results ----

library(readr)

## 1. Load data ----
df <- read_csv("data/input.csv")

## 2. Fit models ----
model <- lm(y ~ x, data = df)

## 3. Export results ----
write_csv(as.data.frame(coef(model)), "results/coefs.csv")
