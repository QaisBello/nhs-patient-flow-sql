# Patient flow: Power BI

A trust activity, beds and inequalities pack on two years of synthetic NHS-style admitted patient care data, with the same definitions as the SQL in this repo.

This folder is a Power BI project (`Patient_Flow.pbip`): a TMDL semantic model and a PBIR report. It is generated from one Python spec, checked against Microsoft's JSON schemas, and its numbers are recomputed independently in pandas.

## Open it

1. Open **`Patient_Flow.pbip`** in Power BI Desktop. In versions before mid-2025, first turn on the preview features for Power BI Project (.pbip), the TMDL model format and the PBIR report format.
2. Click **Refresh**. The model reads this repo's cleaned CSVs from GitHub through the **BaseUrl** parameter. If asked, choose **Anonymous** access for `raw.githubusercontent.com`.
3. Check the visuals against [`docs/expected_values.md`](docs/expected_values.md).

## Pages

- **Activity:** financial-year slicer; emergency and elective admissions, length of stay, readmissions and occupancy; admissions by month; overnight discharges by weekday; a specialty table.
- **Beds:** midnight occupancy against 170 beds by month and every night; nights over 95%.
- **Inequalities:** emergency admission rates by deprivation quintile, crude and age-standardised; the most-to-least deprived gap.

## Model

- **Tables:** Spells, Patients, Deprivation, Age Bands, Population, Specialty, Date.
- **Relationships:** Spells[admission_date] to Date[Date]; Spells[discharge_date] to Date[Date]; Spells[patient_id] to Patients[patient_id]; Spells[treatment_function] to Specialty[treatment_function]; Spells[Age Band 5y] to Age Bands[age_band]; Patients[imd_quintile] to Deprivation[imd_quintile]; Population[imd_quintile] to Deprivation[imd_quintile]; Population[age_band] to Age Bands[age_band].
- **20 DAX measures** in display folders: Activity (Spells Count, Emergency Admissions, Elective Admissions); Length of stay (Mean Length of Stay, Median Length of Stay); Flow (Overnight Discharges, Discharges per Day); Beds (Bed Base, Beds Occupied at Midnight, Average Beds Occupied, Bed Occupancy, Peak Beds Occupied, Nights Over 95%, 95% Line); Readmissions (Readmission Rate (30 days)); Inequalities (Emergency Admissions per Year, Population Count, Crude Rate per 1,000, Age-Standardised Rate per 1,000, Deprivation Gap). The full DAX is in [`docs/measures.md`](docs/measures.md).

## Same answers as the SQL

- **Readmissions** are flagged in Power Query with the rules of `sql/q06.sql` (a self-merge on patient).
- **Midnight occupancy** is a DAX measure (admitted on or before the night, not yet discharged), counted from June 2024 as in `sql/q04.sql`.
- **Discharges by weekday** use an inactive relationship on discharge date, switched on with `USERELATIONSHIP`.
- **Age standardisation** is direct, to the 2013 European Standard Population, in DAX over an age-band dimension that filters both admissions and population.

`tools/expected.py` checks every one of these against `answers/expected.json` (q01, q04, q06, q08, q09): all pass.

## Rebuild and check

```bash
pip install jsonschema referencing pandas numpy
python tools/spec.py        # the spec: writes the .pbip and its folders
python tools/validate.py    # Microsoft schemas, field and DAX references, name clashes
python tools/expected.py    # what the report should show, checked against the project's own results
```

`tools/pbikit.py` is a small shared library for writing Power BI projects as code. It is used across the portfolio and encodes lessons from real Power BI Desktop runs: names are case-insensitive; a format string must not start with a quote; empty CSV cells must become null before a type change; in DAX, `BLANK() = FALSE()` is true.
