-- Q12. Data quality: completeness of ethnicity and deprivation recording for admitted patients,
-- by financial year. Gaps here limit any health inequalities analysis.
SELECT s.financial_year,
       COUNT(DISTINCT s.patient_id)                                                        AS patients,
       ROUND(100.0 * COUNT(DISTINCT CASE WHEN p.ethnic_category = 'Z' THEN s.patient_id END)
             / COUNT(DISTINCT s.patient_id), 1)                                            AS pct_ethnicity_not_stated,
       ROUND(100.0 * COUNT(DISTINCT CASE WHEN p.imd_decile IS NULL THEN s.patient_id END)
             / COUNT(DISTINCT s.patient_id), 1)                                            AS pct_no_deprivation_decile
FROM spells s JOIN patients p USING (patient_id)
GROUP BY s.financial_year
ORDER BY s.financial_year;
