-- Q05. Long-stay patients: how many patients each night had been in hospital 21+ days
-- ("super-stranded"), and what share of occupied beds they took up. Monthly averages.
-- Both counts are running totals of daily in/out events (window functions), so the query stays fast.
WITH RECURSIVE days(d) AS (
  SELECT '2024-04-01' UNION ALL SELECT date(d, '+1 day') FROM days WHERE d < '2026-03-31'
),
adm AS (SELECT admission_date AS d, COUNT(*) AS n FROM spells GROUP BY admission_date),
dis AS (SELECT discharge_date AS d, COUNT(*) AS n FROM spells WHERE discharge_date IS NOT NULL GROUP BY discharge_date),
occupied AS (
  SELECT days.d, SUM(COALESCE(adm.n, 0) - COALESCE(dis.n, 0)) OVER (ORDER BY days.d) AS occupied
  FROM days LEFT JOIN adm ON adm.d = days.d LEFT JOIN dis ON dis.d = days.d
),
-- A patient counts as "21+ days" from the night of day 21 until discharge: +1 on that date, -1 on discharge.
long_in AS (SELECT date(admission_date, '+21 days') AS d, COUNT(*) AS n FROM spells
            WHERE los_days > 21 OR discharge_date IS NULL GROUP BY 1),
long_out AS (SELECT discharge_date AS d, COUNT(*) AS n FROM spells WHERE los_days > 21 GROUP BY 1),
nightly AS (
  SELECT o.d, o.occupied,
         SUM(COALESCE(li.n, 0) - COALESCE(lo.n, 0)) OVER (ORDER BY o.d) AS stayed_21_plus
  FROM occupied o LEFT JOIN long_in li ON li.d = o.d LEFT JOIN long_out lo ON lo.d = o.d
)
SELECT strftime('%Y-%m', d)                                  AS month,
       ROUND(AVG(stayed_21_plus), 1)                         AS avg_patients_21_plus_days,
       ROUND(100.0 * SUM(stayed_21_plus) / SUM(occupied), 1) AS pct_of_occupied_beds
FROM nightly
WHERE d >= '2024-06-01'
GROUP BY month
ORDER BY month;
