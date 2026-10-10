-- Q01. Monthly admitted activity: emergency vs elective spells, by month of admission.
SELECT strftime('%Y-%m', admission_date)            AS month,
       SUM(admission_group = 'Emergency')            AS emergency_spells,
       SUM(admission_group = 'Elective')             AS elective_spells,
       COUNT(*)                                      AS all_spells
FROM spells
GROUP BY month
ORDER BY month;
