"""Generate a synthetic admitted patient care (APC) extract for a fictional acute trust.

Nothing here is real patient data. The structure mirrors what a trust analyst works with in SUS/HES-style
extracts: patients, hospital spells, consultant episodes, diagnoses and procedures, coded with
NHS Data Dictionary values (admission method, discharge method/destination, treatment function).

Built-in behaviour (so the SQL questions have something real to find):
  * winter pressure on emergency admissions, and a Monday peak
  * fewer discharges at weekends, which lengthens some stays
  * a deprivation gradient in emergency admission rates
  * emergency readmission risk that rises with age, frailty and some conditions
  * a small number of deliberate data quality issues (ethnicity not stated, missing deprivation decile)

Run:  python src/generate.py      (deterministic: fixed seed)
"""
import os
from datetime import date, timedelta

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "raw")
RNG = np.random.default_rng(20260401)

START, END = date(2024, 4, 1), date(2026, 3, 31)          # two NHS financial years
PROVIDER = "XSG"                                           # fictional provider code
POP = 85_000                                              # catchment population

# ---------------------------------------------------------------- population
AGE_BANDS = [(0, 4), (5, 9), (10, 14), (15, 19), (20, 24), (25, 29), (30, 34), (35, 39), (40, 44), (45, 49),
             (50, 54), (55, 59), (60, 64), (65, 69), (70, 74), (75, 79), (80, 84), (85, 89), (90, 99)]
AGE_SHARE = np.array([5.6, 6.0, 6.0, 5.6, 6.0, 6.6, 6.8, 6.7, 6.3, 6.2, 6.6, 6.5, 5.8, 5.0, 4.8, 3.6, 2.4, 1.4, 0.8])
AGE_SHARE = AGE_SHARE / AGE_SHARE.sum()
ETHNIC = ["A", "B", "C", "D", "E", "F", "G", "H", "J", "K", "L", "M", "N", "P", "R", "S"]   # NHS ethnic category codes
ETHNIC_P = np.array([62, 2, 4, 1, 1, 1, 1, 4, 3, 1, 2, 5, 3, 1, 3, 6], float)
ETHNIC_P /= ETHNIC_P.sum()
PRACTICES = [f"P8{n:04d}" for n in range(1, 13)]


def make_population():
    band = RNG.choice(len(AGE_BANDS), POP, p=AGE_SHARE)
    lo = np.array([b[0] for b in AGE_BANDS])[band]
    hi = np.array([b[1] for b in AGE_BANDS])[band]
    age0 = lo + (RNG.random(POP) * (hi - lo + 1)).astype(int)            # age on 1 Apr 2024
    sex = RNG.choice(["1", "2"], POP)                                      # 1 male, 2 female (NHS Person Stated Gender)
    imd = RNG.choice(np.arange(1, 11), POP, p=np.array([13, 12, 11, 10, 10, 9, 9, 9, 9, 8]) / 100)
    frail = RNG.gamma(2.0, 0.5, POP) * (1 + np.clip(age0 - 65, 0, None) / 12)
    pop = pd.DataFrame(dict(age0=age0, sex=sex, imd_decile=imd, frailty=frail,
                            ethnic=RNG.choice(ETHNIC, POP, p=ETHNIC_P),
                            practice=RNG.choice(PRACTICES, POP)))
    # long-term conditions belong to the person, not the admission: prevalence rises with age; dementia with frailty too
    agef = np.clip((age0 - 25) / 45, 0.02, 1.6)
    for code, _, prev in COMORB:
        p = prev * agef * (np.clip(frail / 2.5, 0.3, 2.5) if code == "F03" else 1)
        if code == "F03":
            p = np.where(age0 < 60, 0, p)
        pop[code] = RNG.random(POP) < np.clip(p, 0, 0.9)
    pop["dob"] = [date(2024, 4, 1) - timedelta(days=int(a * 365.25 + RNG.integers(0, 365))) for a in pop.age0]
    return pop


# ---------------------------------------------------------------- clinical mix
# primary diagnosis (ICD-10), description, age group, specialty (treatment function), median LOS days, LOS spread,
# in-hospital death probability, base readmission propensity
EMERGENCY_DX = [
    ("J18.9", "Pneumonia, unspecified", "older", "300", 5.5, 0.75, 0.08, 1.4),
    ("N39.0", "Urinary tract infection, site not specified", "older", "430", 4.5, 0.75, 0.02, 1.3),
    ("I50.9", "Heart failure, unspecified", "older", "320", 6.0, 0.70, 0.06, 1.8),
    ("J44.1", "COPD with acute exacerbation", "older", "340", 4.0, 0.70, 0.03, 1.9),
    ("S72.0", "Fracture of neck of femur", "older", "110", 11.0, 0.55, 0.06, 1.0),
    ("A41.9", "Sepsis, unspecified", "older", "300", 7.0, 0.80, 0.12, 1.3),
    ("N17.9", "Acute kidney failure, unspecified", "older", "300", 6.0, 0.75, 0.07, 1.4),
    ("I63.9", "Cerebral infarction, unspecified", "older", "328", 9.0, 0.80, 0.09, 1.0),
    ("F05.9", "Delirium, unspecified", "older", "430", 9.0, 0.70, 0.04, 1.5),
    ("R07.4", "Chest pain, unspecified", "adult", "300", 0.7, 0.90, 0.00, 0.6),
    ("R10.4", "Other and unspecified abdominal pain", "adult", "100", 1.2, 0.90, 0.00, 0.8),
    ("K35.8", "Acute appendicitis, other and unspecified", "adult", "100", 2.5, 0.55, 0.00, 0.5),
    ("L03.1", "Cellulitis of other parts of limb", "adult", "300", 3.5, 0.70, 0.00, 0.9),
    ("J45.9", "Asthma, unspecified", "adult", "340", 1.5, 0.70, 0.00, 1.0),
    ("I21.9", "Acute myocardial infarction, unspecified", "older", "320", 3.5, 0.60, 0.04, 1.1),
    ("K80.2", "Calculus of gallbladder without cholecystitis", "adult", "100", 2.0, 0.70, 0.00, 0.9),
    ("E10.1", "Type 1 diabetes mellitus with ketoacidosis", "adult", "307", 2.5, 0.60, 0.00, 1.6),
    ("J21.9", "Acute bronchiolitis, unspecified", "child", "420", 1.8, 0.65, 0.00, 0.8),
    ("A09.9", "Gastroenteritis and colitis of unspecified origin", "child", "420", 1.0, 0.70, 0.00, 0.6),
    ("B34.9", "Viral infection, unspecified", "child", "420", 0.8, 0.70, 0.00, 0.5),
]
ELECTIVE = [  # OPCS-4 procedure, description, specialty, day-case probability, median LOS if inpatient
    ("C75.1", "Insertion of prosthetic replacement for lens (cataract surgery)", "130", 0.98, 1, "H25.9"),
    ("W40.1", "Primary total prosthetic replacement of knee joint", "110", 0.05, 3, "M17.9"),
    ("W37.1", "Primary total prosthetic replacement of hip joint", "110", 0.05, 3, "M16.9"),
    ("T20.2", "Primary repair of inguinal hernia", "100", 0.85, 1, "K40.9"),
    ("J18.3", "Laparoscopic cholecystectomy", "100", 0.60, 1, "K80.2"),
    ("H22.9", "Diagnostic endoscopic examination of colon (colonoscopy)", "301", 0.99, 1, "K63.5"),
    ("G45.1", "Fibreoptic endoscopic examination of upper GI tract", "301", 0.99, 1, "K21.9"),
    ("M45.9", "Diagnostic endoscopic examination of bladder (cystoscopy)", "101", 0.97, 1, "R31.9"),
    ("Q07.4", "Total abdominal hysterectomy", "502", 0.05, 2, "D25.9"),
]
ELECTIVE_P = np.array([18, 6, 5, 9, 7, 20, 17, 12, 6], float)
ELECTIVE_P /= ELECTIVE_P.sum()
COMORB = [("I10", "Essential hypertension", 0.45), ("E11.9", "Type 2 diabetes", 0.22), ("N18.3", "Chronic kidney disease stage 3", 0.16),
          ("I48.9", "Atrial fibrillation", 0.18), ("F03", "Dementia, unspecified", 0.12), ("J44.9", "COPD", 0.12)]


def age_group(a):
    return "child" if a < 16 else ("adult" if a < 65 else "older")


def main():
    os.makedirs(OUT, exist_ok=True)
    pop = make_population()
    days = pd.date_range(START, END, freq="D")

    # person-level emergency propensity: age, deprivation, frailty
    age = pop.age0.values
    age_rate = np.where(age < 5, 0.09, np.where(age < 16, 0.035, np.where(age < 45, 0.045,
               np.where(age < 65, 0.07, np.where(age < 75, 0.13, np.where(age < 85, 0.24, 0.42))))))
    dep = 1 + (10 - pop.imd_decile.values) * 0.075                      # most deprived ~1.7x least deprived
    w = age_rate * dep * (0.6 + 0.4 * pop.frailty.values / pop.frailty.mean())
    w = w / w.sum()

    groups = {g: [d for d in EMERGENCY_DX if d[2] == g] for g in ("child", "adult", "older")}
    gw = {"child": None, "adult": None, "older": None}

    spells = []
    sid = 0
    pending = []                                                        # (date, person) readmissions

    def add_spell(pid, adm_day, method, dx=None, elective=None):
        nonlocal sid
        p = pop.iloc[pid]
        a = int((adm_day.date() - p.dob).days // 365.25)
        g = age_group(a)
        if elective is None:
            choices = groups[g]
            winter = adm_day.month in (12, 1, 2)
            wts = np.array([1.3 if (winter and c[0] in ("J18.9", "J44.1", "J21.9", "I50.9")) else 1.0 for c in choices])
            c = dx or choices[RNG.choice(len(choices), p=wts / wts.sum())]
            code, desc, _, spec, med, sd, pdie, readm = c
            los = RNG.lognormal(np.log(med * (1 + 0.012 * max(a - 70, 0)) * (1 + 0.25 * (p.frailty > 2.5)) * (1.25 if p["F03"] else 1)), sd)
            proc = None
        else:
            proc_code, proc_desc, spec, pday, med, code = elective
            desc = None
            los = 0 if RNG.random() < pday else RNG.lognormal(np.log(med), 0.4)
            pdie, readm = 0.0005, 0.3
            proc = (proc_code, proc_desc)
        if elective is None and code[0] in "RLKNJ" and RNG.random() < 0.30:   # same-day emergency care, no overnight stay
            los = 0
        los_days = int(round(los)) if los >= 0.5 else 0
        disch = adm_day + pd.Timedelta(days=los_days)
        if los_days > 0 and disch.dayofweek >= 5 and RNG.random() < 0.35:   # weekend discharge slips to Mon/Tue
            disch = disch + pd.Timedelta(days=7 - disch.dayofweek + int(RNG.random() < 0.35))
        died = RNG.random() < pdie * (1 + 0.04 * max(a - 75, 0))
        if died:
            dmeth, ddest = "4", "79"
        else:
            r = RNG.random()
            if a >= 80 and r < 0.10:
                ddest = "85" if RNG.random() < 0.7 else "54"
            elif r < 0.13:
                ddest = "51"
            else:
                ddest = "19"
            dmeth = "2" if (elective is None and RNG.random() < 0.015) else "1"
        sid += 1
        spells.append(dict(spell_id=f"S{sid:06d}", person=pid, admission_date=adm_day.date(), discharge_date=disch.date(),
                           admission_method=method, treatment_function=spec, primary_diagnosis=code, dx_desc=desc,
                           procedure=proc, discharge_method=dmeth, discharge_destination=ddest, age=a))
        # schedule an emergency readmission
        if not died and ddest not in ("51",) and elective is None or (elective is not None and RNG.random() < 0.01):
            prob = 0.058 * readm * (1 + 0.012 * max(a - 60, 0)) * (0.7 + 0.3 * p.frailty) * (1.4 if p["F03"] else 1)
            if RNG.random() < min(prob, 0.6):
                gap = int(RNG.exponential(11)) + 1
                pending.append((disch + pd.Timedelta(days=gap), pid, c if elective is None and RNG.random() < 0.55 else None))
        return disch

    for day in days:
        # emergency volume: winter pressure + Monday peak + noise
        season = 1 + 0.07 * np.cos((day.dayofyear - 15) / 365.25 * 2 * np.pi)
        dow = [1.12, 1.03, 1.0, 1.0, 1.02, 0.92, 0.9][day.dayofweek]
        n_em = RNG.poisson(19 * season * dow)
        for pid in RNG.choice(POP, n_em, p=w):
            m = RNG.choice(["21", "22", "24", "2B"], p=[0.78, 0.15, 0.05, 0.02])
            add_spell(int(pid), day, m)
        # readmissions due today
        due = [x for x in pending if x[0].normalize() == day]
        pending = [x for x in pending if x[0].normalize() != day]
        for _, pid, dx in due:
            add_spell(pid, day, "21", dx=dx)
        # elective: weekdays only, fewer in August and over Christmas
        if day.dayofweek < 5 and not (day.month == 12 and day.day >= 24) and not (day.month == 1 and day.day == 1):
            n_el = RNG.poisson(15 * (0.8 if day.month == 8 else 1.0))
            for _ in range(n_el):
                e = ELECTIVE[RNG.choice(len(ELECTIVE), p=ELECTIVE_P)]
                ok = False
                while not ok:
                    pid = int(RNG.integers(0, POP))
                    a = pop.age0.iat[pid]
                    ok = a >= 18 and (e[2] != "502" or pop.sex.iat[pid] == "2") and RNG.random() < (0.25 + a / 100)
                add_spell(pid, day, RNG.choice(["11", "12"], p=[0.7, 0.3]), elective=e)

    sp = pd.DataFrame(spells)
    sp = sp[sp.admission_date <= END].reset_index(drop=True)
    still_in = sp.discharge_date > END                                  # unfinished spells: no discharge yet
    sp.loc[still_in, ["discharge_date", "discharge_method", "discharge_destination"]] = None

    # ---------------------------------------------------------------- patients (pseudonymised)
    used = sorted(sp.person.unique())
    key = {p: f"{RNG.integers(10**9, 10**10)}" for p in used}            # random pseudonym, not derivable from anything real
    pts = pop.loc[used].copy()
    pts["patient_id"] = [key[p] for p in used]
    pts["birth_month"] = [d.strftime("%Y-%m") for d in pts.dob]          # month and year only
    miss_eth = RNG.random(len(pts)) < 0.06
    pts.loc[miss_eth, "ethnic"] = "Z"                                    # not stated
    miss_imd = RNG.random(len(pts)) < 0.02
    pts["imd_decile"] = pts.imd_decile.astype("Int64")
    pts.loc[miss_imd, "imd_decile"] = pd.NA                              # postcode could not be mapped
    patients = pts[["patient_id", "sex", "birth_month", "ethnic", "imd_decile", "practice"]].rename(
        columns={"ethnic": "ethnic_category", "practice": "gp_practice_code"})

    sp["patient_id"] = sp.person.map(key)
    sp["provider_code"] = PROVIDER
    sp["age_on_admission"] = sp.age
    spells_out = sp[["spell_id", "patient_id", "provider_code", "admission_date", "discharge_date", "admission_method",
                     "treatment_function", "primary_diagnosis", "discharge_method", "discharge_destination", "age_on_admission"]]

    # ---------------------------------------------------------------- consultant episodes (FCEs)
    eps, dxs, procs = [], [], []
    for r in sp.itertuples():
        open_spell = pd.isna(r.discharge_date)
        a = pd.Timestamp(r.admission_date)
        d = pd.Timestamp(END) if open_spell else pd.Timestamp(r.discharge_date)
        los = (d - a).days
        n = 1
        if r.admission_method.startswith("2") and los >= 3:
            n = RNG.choice([1, 2, 3], p=[0.62, 0.30, 0.08])
        cuts = sorted(RNG.choice(range(1, los), n - 1, replace=False)) if n > 1 else []
        bounds = [a] + [a + pd.Timedelta(days=int(c)) for c in cuts] + [d]
        specs = [r.treatment_function] + ["430" if r.age_on_admission >= 75 else "300"] * (n - 1)
        for i in range(n):
            eps.append(dict(episode_id=f"{r.spell_id}-{i + 1}", spell_id=r.spell_id, episode_order=i + 1,
                            treatment_function=specs[i], episode_start=bounds[i].date(),
                            episode_end=None if (open_spell and i == n - 1) else bounds[i + 1].date(),
                            consultant_code=f"C{1000 + (int(r.spell_id[1:]) * 7 + int(specs[i])) % 60}"))
        dxs.append(dict(spell_id=r.spell_id, position=1, icd10_code=r.primary_diagnosis))
        pos = 2
        for code, _, _ in COMORB:                                       # coded on ~90% of spells where present
            if pop[code].iat[r.person] and RNG.random() < 0.9:
                dxs.append(dict(spell_id=r.spell_id, position=pos, icd10_code=code))
                pos += 1
    for r in sp[sp.procedure.notna()].itertuples():
        procs.append(dict(spell_id=r.spell_id, position=1, opcs4_code=r.procedure[0], procedure_date=r.admission_date))
    episodes = pd.DataFrame(eps)
    diagnoses = pd.DataFrame(dxs)
    procedures = pd.DataFrame(procs)

    # ---------------------------------------------------------------- reference tables
    ref_dx = pd.DataFrame([(d[0], d[1]) for d in EMERGENCY_DX] + [(e[5], None) for e in ELECTIVE] + [(c[0], c[1]) for c in COMORB],
                          columns=["icd10_code", "description"]).drop_duplicates("icd10_code")
    names = {"H25.9": "Senile cataract, unspecified", "M17.9": "Gonarthrosis (knee osteoarthritis), unspecified",
             "M16.9": "Coxarthrosis (hip osteoarthritis), unspecified", "K40.9": "Unilateral inguinal hernia",
             "K63.5": "Polyp of colon", "K21.9": "Gastro-oesophageal reflux disease without oesophagitis",
             "R31.9": "Haematuria, unspecified", "D25.9": "Leiomyoma of uterus, unspecified"}
    ref_dx["description"] = ref_dx.apply(lambda x: x.description or names.get(x.icd10_code), axis=1)
    ref_proc = pd.DataFrame([(e[0], e[1]) for e in ELECTIVE], columns=["opcs4_code", "description"])
    ref_tf = pd.DataFrame([("100", "General Surgery"), ("101", "Urology"), ("110", "Trauma and Orthopaedics"),
                           ("130", "Ophthalmology"), ("300", "General Internal Medicine"), ("301", "Gastroenterology"),
                           ("307", "Diabetes"), ("320", "Cardiology"), ("328", "Stroke Medicine"), ("340", "Respiratory Medicine"),
                           ("420", "Paediatrics"), ("430", "Elderly Medicine"), ("502", "Gynaecology")],
                          columns=["treatment_function", "description"])
    ref_am = pd.DataFrame([("11", "Elective: waiting list", "Elective"), ("12", "Elective: booked", "Elective"),
                           ("21", "Emergency: via Emergency Care Department", "Emergency"),
                           ("22", "Emergency: GP request", "Emergency"), ("24", "Emergency: consultant clinic", "Emergency"),
                           ("2B", "Emergency: transfer from another provider", "Emergency")],
                          columns=["admission_method", "description", "admission_group"])
    ref_dd = pd.DataFrame([("19", "Usual place of residence"), ("51", "NHS other hospital provider: general ward"),
                           ("54", "NHS-run care home"), ("79", "Not applicable: patient died"),
                           ("85", "Non-NHS run care home")], columns=["discharge_destination", "description"])
    ref_dm = pd.DataFrame([("1", "Discharged on clinical advice"), ("2", "Self-discharged"), ("4", "Died")],
                          columns=["discharge_method", "description"])

    # population denominators by 5-year band, sex and IMD quintile (mid-period registered list)
    pop["band"] = pd.cut(pop.age0, [b[0] - 0.5 for b in AGE_BANDS] + [120], labels=[f"{b[0]}-{b[1]}" if b[1] < 99 else "90+" for b in AGE_BANDS])
    pop["imd_quintile"] = (pop.imd_decile + 1) // 2
    popn = pop.groupby(["band", "sex", "imd_quintile"], observed=True).size().reset_index(name="population")
    popn = popn.rename(columns={"band": "age_band"})
    esp = pd.DataFrame({"age_band": [f"{b[0]}-{b[1]}" if b[1] < 99 else "90+" for b in AGE_BANDS],
                        "esp2013_weight": [5000, 5500, 5500, 5500, 6000, 6000, 6500, 7000, 7000, 7000, 7000, 6500, 6000,
                                           5500, 5000, 4000, 2500, 1500, 1000]})

    files = dict(patients=patients, spells=spells_out, episodes=episodes, diagnoses=diagnoses, procedures=procedures,
                 ref_icd10=ref_dx, ref_opcs4=ref_proc, ref_treatment_function=ref_tf, ref_admission_method=ref_am,
                 ref_discharge_destination=ref_dd, ref_discharge_method=ref_dm, population=popn, ref_esp2013=esp)
    files["patients"], files["spells"], files["episodes"], files["diagnoses"] = make_messy(patients, spells_out, episodes, diagnoses)
    for n, df in files.items():
        df.to_csv(os.path.join(OUT, f"{n}.csv"), index=False)
        print(f"{n:28s} {len(df):>7,} rows")


def make_messy(patients, spells, episodes, diagnoses):
    """Add the data quality problems a real extract arrives with. src/clean.py has to find and fix every one."""
    m = np.random.default_rng(7)
    p, s, e, d = patients.copy(), spells.copy(), episodes.copy(), diagnoses.copy()
    for col in ("admission_date", "discharge_date"):
        s[col] = s[col].map(lambda v: None if pd.isna(v) else str(v))
    finished = s.discharge_date.notna()
    # 1. resubmitted records: exact duplicate rows
    s = pd.concat([s, s.sample(frac=0.006, random_state=1)]).sort_values("spell_id").reset_index(drop=True)
    e = pd.concat([e, e.sample(frac=0.004, random_state=2)]).sort_values("episode_id").reset_index(drop=True)
    p = pd.concat([p, p.sample(frac=0.003, random_state=3)]).reset_index(drop=True)
    # 2. mixed date formats: some rows arrive as DD/MM/YYYY
    finished = s.discharge_date.notna()
    k = (m.random(len(s)) < 0.05) & finished
    for col in ("admission_date", "discharge_date"):
        s.loc[k, col] = pd.to_datetime(s.loc[k, col]).dt.strftime("%d/%m/%Y")
    # 3. ICD-10 codes without the dot (as HES stores them) and stray whitespace in codes
    k = m.random(len(s)) < 0.12
    s.loc[k, "primary_diagnosis"] = s.loc[k, "primary_diagnosis"].str.replace(".", "", regex=False)
    k = m.random(len(d)) < 0.10
    d.loc[k, "icd10_code"] = d.loc[k, "icd10_code"].str.replace(".", "", regex=False)
    k = m.random(len(s)) < 0.02
    s.loc[k, "admission_method"] = s.loc[k, "admission_method"] + " "
    # 4. invalid treatment function on the spell (recoverable from the first episode)
    k = m.random(len(s)) < 0.004
    s.loc[k, "treatment_function"] = "999"
    # 5. discharge before admission (keying error) and a placeholder discharge date
    k = np.where((m.random(len(s)) < 0.002) & finished & (s.admission_date != s.discharge_date))[0]
    s.loc[k, ["admission_date", "discharge_date"]] = s.loc[k, ["discharge_date", "admission_date"]].values
    k = np.where((m.random(len(s)) < 0.002) & finished)[0]
    s.loc[k, "discharge_date"] = "1900-01-01"
    # 6. patient codes in the wrong case
    k = m.random(len(p)) < 0.03
    p.loc[k, "ethnic_category"] = p.loc[k, "ethnic_category"].str.lower()
    return p, s, e, d


if __name__ == "__main__":
    main()
