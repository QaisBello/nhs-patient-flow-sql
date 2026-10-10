-- Q11. Crude in-hospital mortality for emergency spells by primary diagnosis (100+ spells).
-- Crude rates are not risk-adjusted: they reflect case mix as much as quality of care.
SELECT r.description                                                     AS primary_diagnosis,
       s.primary_diagnosis                                               AS icd10,
       COUNT(*)                                                          AS spells,
       SUM(s.discharge_method = '4')                                     AS deaths,
       ROUND(100.0 * SUM(s.discharge_method = '4') / COUNT(*), 1)        AS crude_mortality_pct,
       ROUND(AVG(s.age_on_admission), 0)                                 AS mean_age
FROM spells s
JOIN ref_icd10 r ON r.icd10_code = s.primary_diagnosis
WHERE s.admission_group = 'Emergency' AND s.discharge_date IS NOT NULL
GROUP BY s.primary_diagnosis
HAVING COUNT(*) >= 100
ORDER BY crude_mortality_pct DESC, spells DESC;
