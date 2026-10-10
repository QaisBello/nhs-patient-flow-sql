-- Q09. Emergency admissions per 1,000 population per year by deprivation quintile (1 = most deprived),
-- crude and directly age-standardised to the 2013 European Standard Population.
-- Patients with no recorded deprivation decile are excluded (see the data quality log).
WITH em AS (
  SELECT (p.imd_decile + 1) / 2 AS imd_quintile,
         CASE WHEN s.age_on_admission >= 90 THEN '90+'
              ELSE (s.age_on_admission / 5 * 5) || '-' || (s.age_on_admission / 5 * 5 + 4) END AS age_band
  FROM spells s JOIN patients p USING (patient_id)
  WHERE s.admission_group = 'Emergency' AND p.imd_decile IS NOT NULL
),
num AS (SELECT imd_quintile, age_band, COUNT(*) / 2.0 AS per_year FROM em GROUP BY 1, 2),
den AS (SELECT imd_quintile, age_band, SUM(population) AS pop FROM population GROUP BY 1, 2),
rates AS (
  SELECT d.imd_quintile, d.age_band, d.pop, COALESCE(n.per_year, 0) AS events, w.esp2013_weight AS w
  FROM den d
  LEFT JOIN num n USING (imd_quintile, age_band)
  JOIN ref_esp2013 w USING (age_band)
)
SELECT imd_quintile,
       CAST(SUM(pop) AS INT)                                     AS population,
       ROUND(SUM(events), 1)                                     AS admissions_per_year,
       ROUND(1000.0 * SUM(events) / SUM(pop), 1)                 AS crude_rate_per_1000,
       ROUND(SUM(1000.0 * events / pop * w) / SUM(w), 1)         AS age_standardised_rate_per_1000
FROM rates
GROUP BY imd_quintile
ORDER BY imd_quintile;
