-- Q02. Spells vs consultant episodes (FCEs). Counting episodes overstates admissions:
-- a patient who moves from one consultant to another has one spell but several episodes.
SELECT s.admission_group,
       COUNT(DISTINCT s.spell_id)                                         AS spells,
       COUNT(e.episode_id)                                                AS episodes,
       ROUND(1.0 * COUNT(e.episode_id) / COUNT(DISTINCT s.spell_id), 3)   AS episodes_per_spell,
       ROUND(100.0 * COUNT(DISTINCT CASE WHEN e.episode_order > 1 THEN s.spell_id END)
             / COUNT(DISTINCT s.spell_id), 1)                             AS pct_spells_multi_episode
FROM spells s
JOIN episodes e ON e.spell_id = s.spell_id
GROUP BY s.admission_group
ORDER BY s.admission_group DESC;
