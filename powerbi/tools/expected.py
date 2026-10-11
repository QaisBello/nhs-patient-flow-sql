"""What the Power BI report should show: every measure's logic recomputed in pandas, then checked against the SQL
answers in answers/expected.json. Run from powerbi/:

    python tools/expected.py        # writes docs/expected_values.md; exit code 1 on any disagreement
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(ROOT)
CLEAN = os.path.join(REPO, "data", "clean")
SQL = json.load(open(os.path.join(REPO, "answers", "expected.json")))
BEDS = 170

sp = pd.read_csv(os.path.join(CLEAN, "spells.csv"), dtype={"discharge_method": str, "discharge_destination": str, "treatment_function": str},
                 parse_dates=["admission_date", "discharge_date"])
pt = pd.read_csv(os.path.join(CLEAN, "patients.csv"))
pop = pd.read_csv(os.path.join(CLEAN, "population.csv"))
esp = pd.read_csv(os.path.join(CLEAN, "ref_esp2013.csv"))
spec = pd.read_csv(os.path.join(CLEAN, "ref_treatment_function.csv"), dtype={"treatment_function": str})
problems = []


def check(label, got, want, tol):
    got, want = np.asarray(got, float), np.asarray(want, float)
    ok = got.shape == want.shape and np.allclose(got, want, atol=tol)
    print(("PASS " if ok else "FAIL ") + label)
    if not ok:
        problems.append(label)


# --- activity by month (q01)
sp["month"] = sp.admission_date.dt.strftime("%Y-%m")
m = sp.pivot_table(index="month", columns="admission_group", values="spell_id", aggfunc="count")
q01 = pd.DataFrame(SQL["q01"]["rows"], columns=SQL["q01"]["columns"]).set_index("month")
check("Emergency and elective admissions by month = SQL q01", m[["Emergency", "Elective"]].values, q01[["emergency_spells", "elective_spells"]].values, 0)

# --- readmissions, Power Query rules (q06)
em = sp[sp.admission_group == "Emergency"][["patient_id", "spell_id", "admission_date"]]
idx = sp[sp.discharge_date.notna() & (sp.discharge_method != "4") & (sp.discharge_destination != "51")
         & (sp.discharge_date <= pd.Timestamp("2026-03-01"))].copy()
j = idx.merge(em, on="patient_id", suffixes=("", "_r"))
j = j[(j.spell_id_r != j.spell_id) & (j.admission_date_r >= j.discharge_date) & (j.admission_date_r <= j.discharge_date + pd.Timedelta(days=30))]
idx["readmitted"] = idx.spell_id.isin(j.spell_id).astype(int)
by_spec = idx.groupby("treatment_function").readmitted.agg(["size", "sum"]).join(spec.set_index("treatment_function"))
q06 = pd.DataFrame(SQL["q06"]["rows"], columns=SQL["q06"]["columns"]).set_index("index_specialty")
got = by_spec.set_index("description").loc[q06.index]
check("Readmissions by specialty = SQL q06", got[["size", "sum"]].values, q06[["index_spells", "readmitted_30d"]].values, 0)
readm = idx.readmitted.mean()

# --- midnight occupancy (q04)
days = pd.date_range("2024-04-01", "2026-03-31")
adm = sp.groupby("admission_date").size().reindex(days, fill_value=0)
dis = sp.dropna(subset=["discharge_date"]).groupby("discharge_date").size().reindex(days, fill_value=0)
occ = (adm - dis).cumsum()
occ = occ[occ.index >= "2024-06-01"]
mo = occ.groupby(occ.index.strftime("%Y-%m")).agg(["mean", "max", lambda s: (s > 0.95 * BEDS).sum()])
q04 = pd.DataFrame(SQL["q04"]["rows"], columns=SQL["q04"]["columns"]).set_index("month")
check("Average beds occupied by month = SQL q04", mo["mean"].values, q04.avg_occupied_beds.values, 0.051)
check("Nights over 95% by month = SQL q04", mo.iloc[:, 2].values, q04.nights_over_95pct.values, 0)

# --- discharges by weekday (q08)
d = sp.dropna(subset=["discharge_date"])
d = d[d.los_days > 0]
wd = d.groupby(d.discharge_date.dt.dayofweek).size()
ndays = pd.Series(days.dayofweek).value_counts().sort_index()
q08 = pd.DataFrame(SQL["q08"]["rows"], columns=SQL["q08"]["columns"])
check("Discharges by weekday = SQL q08", wd.values, q08.discharges.values, 0)
check("Discharges per day by weekday = SQL q08", (wd / ndays).values, q08.avg_per_day.values, 0.051)

# --- age-standardised rates (q09)
pt["imd_quintile"] = (pt.imd_decile + 1) // 2
e = sp[sp.admission_group == "Emergency"].merge(pt[["patient_id", "imd_quintile"]], on="patient_id").dropna(subset=["imd_quintile"])
e["band"] = np.where(e.age_on_admission >= 90, "90+", (e.age_on_admission // 5 * 5).astype(str) + "-" + (e.age_on_admission // 5 * 5 + 4).astype(str))
ev = e.groupby(["imd_quintile", "band"]).size() / 2
den = pop.groupby(["imd_quintile", "age_band"]).population.sum()
w = esp.set_index("age_band").esp2013_weight
rows = []
for qn in range(1, 6):
    dq = den.loc[qn]
    evq = ev.loc[float(qn)].reindex(dq.index, fill_value=0) if float(qn) in ev.index.get_level_values(0) else dq * 0
    asr = (1000 * evq / dq * w.reindex(dq.index)).sum() / w.reindex(dq.index).sum()
    rows.append((qn, dq.sum(), evq.sum(), 1000 * evq.sum() / dq.sum(), asr))
r9 = pd.DataFrame(rows, columns=["q", "pop", "per_year", "crude", "asr"])
q09 = pd.DataFrame(SQL["q09"]["rows"], columns=SQL["q09"]["columns"])
check("Crude and age-standardised rates by quintile = SQL q09", r9[["crude", "asr"]].values, q09[["crude_rate_per_1000", "age_standardised_rate_per_1000"]].values, 0.051)

disc = sp[sp.discharge_date.notna()]
lines = ["# Expected values", "",
         "From `tools/expected.py`: each measure's logic recomputed in pandas and checked against the SQL answers (`answers/expected.json`).", "",
         *[f"- {'FAIL' if l in problems else 'PASS'}: {l}" for l in [
             "Emergency and elective admissions by month = SQL q01", "Readmissions by specialty = SQL q06", "Average beds occupied by month = SQL q04",
             "Nights over 95% by month = SQL q04", "Discharges by weekday = SQL q08", "Discharges per day by weekday = SQL q08",
             "Crude and age-standardised rates by quintile = SQL q09"]],
         "", "## Page 1 cards (no slicer)", "", "| Card | Expected |", "|---|---:|",
         f"| Emergency admissions | {(sp.admission_group == 'Emergency').sum():,} |", f"| Elective admissions | {(sp.admission_group == 'Elective').sum():,} |",
         f"| Mean length of stay (days) | {disc.los_days.mean():.1f} |", f"| Emergency readmission in 30 days (all stays) | {readm:.1%} |",
         f"| Bed occupancy (from Jun 2024) | {occ.mean() / BEDS:.1%} |",
         "", "## Page 2 cards", "", "| Card | Expected |", "|---|---:|",
         f"| Average beds occupied | {occ.mean():.1f} |", f"| Fullest night | {occ.max():.0f} |", f"| Nights over 95% | {(occ > 0.95 * BEDS).sum()} |",
         "", "## Page 3", "", f"Most vs least deprived fifth: **{r9.asr.iloc[0] / r9.asr.iloc[4]:.1f}x**", "",
         "| Quintile | Population | Admissions a year | Crude | Age-standardised |", "|---|---:|---:|---:|---:|"]
lines += [f"| {int(r.q)} | {r['pop']:,.0f} | {r.per_year:,.1f} | {r.crude:.1f} | {r.asr:.1f} |" for _, r in r9.iterrows()]
os.makedirs(os.path.join(ROOT, "docs"), exist_ok=True)
open(os.path.join(ROOT, "docs", "expected_values.md"), "w").write("\n".join(lines) + "\n")
print("\n".join(lines[10:]))
sys.exit(1 if problems else 0)
