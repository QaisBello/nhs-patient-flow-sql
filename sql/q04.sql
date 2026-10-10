-- Q04. Midnight bed occupancy against a general and acute bed base of 170 beds.
-- Beds occupied at midnight = everyone admitted so far minus everyone discharged so far: a running total
-- of daily admissions minus discharges (window function), which is far faster than counting each night.
-- Patients still in hospital at the extract date have no discharge date, so they stay in the total.
WITH RECURSIVE days(d) AS (
  SELECT '2024-04-01' UNION ALL SELECT date(d, '+1 day') FROM days WHERE d < '2026-03-31'
),
adm AS (SELECT admission_date AS d, COUNT(*) AS n FROM spells GROUP BY admission_date),
dis AS (SELECT discharge_date AS d, COUNT(*) AS n FROM spells WHERE discharge_date IS NOT NULL GROUP BY discharge_date),
nightly AS (
  SELECT days.d,
         SUM(COALESCE(adm.n, 0) - COALESCE(dis.n, 0)) OVER (ORDER BY days.d) AS occupied
  FROM days LEFT JOIN adm ON adm.d = days.d LEFT JOIN dis ON dis.d = days.d
)
SELECT strftime('%Y-%m', d)                      AS month,
       ROUND(AVG(occupied), 1)                   AS avg_occupied_beds,
       MAX(occupied)                             AS peak_occupied_beds,
       ROUND(100.0 * AVG(occupied) / 170, 1)     AS avg_occupancy_pct,
       SUM(occupied > 0.95 * 170)                AS nights_over_95pct
FROM nightly
WHERE d >= '2024-06-01'          -- April and May excluded: patients admitted before the extract began are not in it
GROUP BY month
ORDER BY month;
