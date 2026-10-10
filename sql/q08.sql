-- Q08. Discharges by day of the week (overnight stays only), averaged per calendar day.
-- Fewer weekend discharges mean beds stay full into Monday.
WITH RECURSIVE days(d) AS (
  SELECT '2024-04-01' UNION ALL SELECT date(d, '+1 day') FROM days WHERE d < '2026-03-31'
),
n_days AS (SELECT strftime('%w', d) AS dow, COUNT(*) AS n FROM days GROUP BY dow)
SELECT CASE s.dow WHEN '1' THEN 'Mon' WHEN '2' THEN 'Tue' WHEN '3' THEN 'Wed' WHEN '4' THEN 'Thu'
                  WHEN '5' THEN 'Fri' WHEN '6' THEN 'Sat' ELSE 'Sun' END AS weekday,
       s.discharges,
       ROUND(1.0 * s.discharges / n.n, 1)                                 AS avg_per_day
FROM (SELECT strftime('%w', discharge_date) AS dow, COUNT(*) AS discharges
      FROM spells WHERE los_days > 0 AND discharge_date IS NOT NULL GROUP BY dow) s
JOIN n_days n USING (dow)
ORDER BY CASE s.dow WHEN '0' THEN 7 ELSE CAST(s.dow AS INT) END;
