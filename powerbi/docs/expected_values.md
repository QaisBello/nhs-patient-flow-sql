# Expected values

From `tools/expected.py`: each measure's logic recomputed in pandas and checked against the SQL answers (`answers/expected.json`).

- PASS: Emergency and elective admissions by month = SQL q01
- PASS: Readmissions by specialty = SQL q06
- PASS: Average beds occupied by month = SQL q04
- PASS: Nights over 95% by month = SQL q04
- PASS: Discharges by weekday = SQL q08
- PASS: Discharges per day by weekday = SQL q08
- PASS: Crude and age-standardised rates by quintile = SQL q09

## Page 1 cards (no slicer)

| Card | Expected |
|---|---:|
| Emergency admissions | 15,253 |
| Elective admissions | 7,480 |
| Mean length of stay (days) | 4.7 |
| Emergency readmission in 30 days (all stays) | 10.0% |
| Bed occupancy (from Jun 2024) | 89.5% |

## Page 2 cards

| Card | Expected |
|---|---:|
| Average beds occupied | 152.2 |
| Fullest night | 188 |
| Nights over 95% | 153 |

## Page 3

Most vs least deprived fifth: **1.6x**

| Quintile | Population | Admissions a year | Crude | Age-standardised |
|---|---:|---:|---:|---:|
| 1 | 21,152 | 2,203.5 | 104.2 | 108.8 |
| 2 | 17,820 | 1,712.0 | 96.1 | 98.3 |
| 3 | 16,160 | 1,461.5 | 90.4 | 93.5 |
| 4 | 15,447 | 1,153.0 | 74.6 | 78.4 |
| 5 | 14,421 | 936.0 | 64.9 | 69.8 |
