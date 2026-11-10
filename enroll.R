library(tidyverse)

# Combine the six enrollYY[YY].csv files (Big Ten undergrad enrollment by
# race/ethnicity, 2014-2024) into one long table.
enroll <- list.files("data", pattern = "^enroll\\d+\\.csv$", full.names = TRUE) |>
  map(\(f) read_csv(f, show_col_types = FALSE) |>
        select(-starts_with("..."))) |>              # drop the empty column from each trailing comma
  map(\(d) d |>
        pivot_longer(
          starts_with("Percent"),
          names_to = c("race", "year"),
          names_pattern = "Percent of undergraduate enrollment that are (.*) \\(DRVEF(\\d{4})(?:_RV)?\\)",
          values_to = "percent"
        )) |>
  list_rbind() |>
  mutate(
    year = as.integer(year),
    race = if_else(str_detect(race, "Nonresident"), "Nonresident", race)
  ) |>
  rename(unit_id = UnitID, school = `Institution Name`) |>
  arrange(school, race, year)

write_csv(enroll, "data/big_ten_enrollment_long.csv")

# Wide table: 2014 vs. 2024 share and change, one row per school and race.
# Drops the combined Asian/NHPI category, which overlaps with Asian and NHPI.
change <- enroll |>
  filter(year %in% c(2014, 2024),
         race != "Asian/Native Hawaiian/Pacific Islander") |>
  pivot_wider(names_from = year, values_from = percent, names_prefix = "y") |>
  mutate(change = y2024 - y2014) |>
  arrange(race, desc(change))

write_csv(change, "data/big_ten_enrollment_change.csv")

# Each school should have 11 years for every race category
enroll |> count(school, race) |> distinct(n)
