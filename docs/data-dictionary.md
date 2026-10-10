# Data dictionary (data/clean)

All data is synthetic. Codes follow the NHS Data Dictionary, ICD-10 and OPCS-4.

## patients
| Column | Meaning |
|---|---|
| patient_id | Random 10-digit pseudonym (not derivable from anything real) |
| sex | 1 male, 2 female |
| birth_month | Month and year of birth only (YYYY-MM) |
| ethnic_category | NHS ethnic category code (A–S; Z = not stated) |
| imd_decile | Index of Multiple Deprivation decile of residence, 1 = most deprived; blank if the postcode could not be mapped |
| gp_practice_code | Registered GP practice (fictional) |

## spells (one row per hospital stay)
| Column | Meaning |
|---|---|
| spell_id, patient_id, provider_code | Keys; XSG is a fictional provider |
| admission_date, discharge_date | ISO dates; discharge blank if the patient was still in hospital at the extract date |
| admission_method | 11 waiting list, 12 booked (elective); 21 via emergency department, 22 GP request, 24 consultant clinic, 2B transfer (emergency) |
| treatment_function | Specialty of the spell (e.g. 300 General Internal Medicine, 430 Elderly Medicine) |
| primary_diagnosis | ICD-10 code, dotted form |
| discharge_method | 1 clinical advice, 2 self-discharge, 4 died |
| discharge_destination | 19 usual residence, 51 other NHS hospital, 54/85 care home, 79 died |
| age_on_admission, age_band | Age in years and analysis band |
| los_days | Discharge minus admission date (0 = same day); blank for unfinished spells |
| admission_group | Elective or Emergency, derived from admission_method |
| financial_year | NHS financial year of admission (April–March) |

## episodes (finished consultant episodes)
episode_id, spell_id, episode_order (1 = first consultant), treatment_function, episode_start, episode_end (blank if ongoing), consultant_code.

## diagnoses / procedures
diagnoses: spell_id, position (1 = primary), icd10_code. procedures: spell_id, position, opcs4_code, procedure_date.

## population, ref_esp2013
Registered population by 5-year age band, sex and deprivation quintile (denominators for rates), and the 2013 European Standard Population weights used for direct age standardisation.

## data_quality_log, rejected_spells
Every cleaning check with rows affected and the action taken; spells excluded from analysis and why.
