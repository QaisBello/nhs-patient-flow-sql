-- Q10. Frequent attenders: patients with 3 or more emergency admissions within any 365-day period,
-- and the share of emergency bed days they account for. Uses a RANGE window over the date.
WITH em AS (
  SELECT patient_id, spell_id, los_days,
         COUNT(*) OVER (PARTITION BY patient_id ORDER BY julianday(admission_date)
                        RANGE BETWEEN 364 PRECEDING AND CURRENT ROW) AS in_last_year
  FROM spells WHERE admission_group = 'Emergency'
),
frequent AS (SELECT DISTINCT patient_id FROM em WHERE in_last_year >= 3)
SELECT (SELECT COUNT(*) FROM frequent)                                              AS frequent_attenders,
       (SELECT COUNT(DISTINCT patient_id) FROM em)                                  AS patients_with_emergency_admission,
       ROUND(100.0 * (SELECT COUNT(*) FROM frequent) / (SELECT COUNT(DISTINCT patient_id) FROM em), 1) AS pct_of_patients,
       ROUND(100.0 * SUM(CASE WHEN patient_id IN (SELECT patient_id FROM frequent) THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_of_emergency_spells,
       ROUND(100.0 * SUM(CASE WHEN patient_id IN (SELECT patient_id FROM frequent) THEN COALESCE(los_days, 0) ELSE 0 END) / SUM(COALESCE(los_days, 0)), 1) AS pct_of_emergency_bed_days
FROM em;
