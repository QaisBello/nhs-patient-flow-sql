-- Q06. Emergency readmissions within 30 days of discharge, by specialty of the first (index) spell.
-- Index spells: discharged alive, not transferred to another hospital, and discharged at least
-- 30 days before the end of the data so every index spell has a full 30-day follow-up window.
WITH idx AS (
  SELECT s.*
  FROM spells s
  WHERE s.discharge_date IS NOT NULL
    AND s.discharge_method <> '4'
    AND s.discharge_destination <> '51'
    AND s.discharge_date <= date('2026-03-31', '-30 days')
),
flagged AS (
  SELECT i.spell_id, i.treatment_function, i.admission_group,
         EXISTS (SELECT 1 FROM spells r
                 WHERE r.patient_id = i.patient_id
                   AND r.admission_group = 'Emergency'
                   AND r.spell_id <> i.spell_id
                   AND r.admission_date >= i.discharge_date
                   AND r.admission_date <= date(i.discharge_date, '+30 days')) AS readmitted
  FROM idx i
)
SELECT t.description                              AS index_specialty,
       COUNT(*)                                   AS index_spells,
       SUM(readmitted)                            AS readmitted_30d,
       ROUND(100.0 * SUM(readmitted) / COUNT(*), 1) AS readmission_rate_pct
FROM flagged f
JOIN ref_treatment_function t USING (treatment_function)
GROUP BY f.treatment_function
HAVING COUNT(*) >= 200
ORDER BY readmission_rate_pct DESC;
