-- Q03. Emergency length of stay by specialty: mean, median and share discharged the same day.
-- SQLite has no MEDIAN(), so it is computed with ROW_NUMBER() over each specialty.
WITH ranked AS (
  SELECT treatment_function, los_days,
         ROW_NUMBER() OVER (PARTITION BY treatment_function ORDER BY los_days) AS rn,
         COUNT(*)     OVER (PARTITION BY treatment_function)                   AS n
  FROM spells
  WHERE admission_group = 'Emergency' AND discharge_date IS NOT NULL   -- finished spells only
)
SELECT t.description                                                  AS specialty,
       r.n                                                            AS spells,
       ROUND(AVG(r.los_days), 1)                                      AS mean_los,
       AVG(CASE WHEN r.rn IN ((r.n + 1) / 2, (r.n + 2) / 2) THEN r.los_days END) AS median_los,
       ROUND(100.0 * SUM(r.los_days = 0) / r.n, 1)                    AS pct_same_day
FROM ranked r
JOIN ref_treatment_function t USING (treatment_function)
GROUP BY r.treatment_function
HAVING r.n >= 100
ORDER BY mean_los DESC;
