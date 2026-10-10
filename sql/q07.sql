-- Q07. 30-day emergency readmission after an emergency spell, by age band, split by whether the
-- patient has dementia coded as a secondary diagnosis (ICD-10 F03), a common frailty marker.
WITH idx AS (
  SELECT s.*,
         EXISTS (SELECT 1 FROM diagnoses d WHERE d.spell_id = s.spell_id AND d.icd10_code = 'F03') AS dementia
  FROM spells s
  WHERE s.admission_group = 'Emergency'
    AND s.discharge_date IS NOT NULL
    AND s.discharge_method <> '4'
    AND s.discharge_destination <> '51'
    AND s.discharge_date <= date('2026-03-31', '-30 days')
),
flagged AS (
  SELECT i.age_band, i.dementia,
         EXISTS (SELECT 1 FROM spells r
                 WHERE r.patient_id = i.patient_id AND r.admission_group = 'Emergency'
                   AND r.spell_id <> i.spell_id
                   AND r.admission_date BETWEEN i.discharge_date AND date(i.discharge_date, '+30 days')) AS readmitted
  FROM idx i
)
SELECT age_band,
       COUNT(*)                                                          AS index_spells,
       ROUND(100.0 * AVG(readmitted), 1)                                 AS readmission_rate_pct,
       ROUND(100.0 * AVG(CASE WHEN dementia = 1 THEN readmitted END), 1) AS with_dementia_pct,
       ROUND(100.0 * AVG(CASE WHEN dementia = 0 THEN readmitted END), 1) AS without_dementia_pct
FROM flagged
GROUP BY age_band
ORDER BY CASE age_band WHEN '0-15' THEN 1 WHEN '16-44' THEN 2 WHEN '45-64' THEN 3
                       WHEN '65-74' THEN 4 WHEN '75-84' THEN 5 ELSE 6 END;
