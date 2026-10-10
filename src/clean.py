"""Clean the raw APC extract (data/raw) into analysis-ready tables (data/clean).

Every check writes a row to data/clean/data_quality_log.csv: what was checked, how many rows it touched,
and what was done. Records that cannot be trusted are excluded and kept in data/clean/rejected_spells.csv,
the way a trust would send them back to the provider for correction rather than silently drop them.

Run:  python src/clean.py
"""
import os
import re

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW, OUT = os.path.join(ROOT, "data", "raw"), os.path.join(ROOT, "data", "clean")
LOG = []


def log(table, check, rows, finding, action):
    LOG.append(dict(table=table, check=check, rows_affected=int(rows), finding=finding, action=action))


def read(name):
    return pd.read_csv(os.path.join(RAW, f"{name}.csv"), dtype=str, keep_default_na=False, na_values=[""])


def icd_dot(code):
    """ICD-10 arrives both as J18.9 and J189: standardise to the dotted form."""
    if pd.isna(code):
        return code
    code = code.strip().upper()
    return code if "." in code or len(code) <= 3 else f"{code[:3]}.{code[3:]}"


def parse_dates(series):
    iso = pd.to_datetime(series, format="%Y-%m-%d", errors="coerce")
    uk = pd.to_datetime(series, format="%d/%m/%Y", errors="coerce")
    return iso.fillna(uk), int(iso.isna().sum() - (iso.isna() & uk.isna()).sum())


def main():
    os.makedirs(OUT, exist_ok=True)

    # ------------------------------------------------------------ patients
    p = read("patients")
    log("patients", "Rows received", len(p), f"{len(p):,} patient rows", "-")
    n = (p.ethnic_category != p.ethnic_category.str.upper()).sum()
    p["ethnic_category"] = p.ethnic_category.str.upper()
    log("patients", "Ethnic category case", n, "Lower-case codes (e.g. 'a' for 'A')", "Upper-cased")
    n = p.duplicated().sum()
    p = p.drop_duplicates()
    log("patients", "Duplicate patient rows", n, "Same pseudonymised patient sent twice", "Kept one")
    log("patients", "Ethnicity not stated", (p.ethnic_category == "Z").sum(), "Coded Z (not stated)",
        "Kept; reported as its own group")
    log("patients", "No deprivation decile", p.imd_decile.isna().sum(), "Postcode could not be mapped to an LSOA",
        "Kept; left out of deprivation analysis only")
    assert not p.patient_id.duplicated().any(), "patient_id must be unique after de-duplication"

    # ------------------------------------------------------------ spells
    s = read("spells")
    log("spells", "Rows received", len(s), f"{len(s):,} spell rows", "-")
    for c in ("admission_method", "treatment_function", "discharge_method", "discharge_destination", "primary_diagnosis"):
        n = (s[c].notna() & (s[c] != s[c].str.strip())).sum()
        s[c] = s[c].str.strip()
        if n:
            log("spells", f"Whitespace in {c}", n, "Trailing spaces in a code field", "Trimmed")
    s["admission_date"], n1 = parse_dates(s.admission_date)
    placeholder = s.discharge_date == "1900-01-01"
    s["discharge_date"], n2 = parse_dates(s.discharge_date)
    log("spells", "Date format", n1 + n2, "Dates sent as DD/MM/YYYY instead of YYYY-MM-DD", "Parsed both formats")
    before = s.primary_diagnosis.copy()
    s["primary_diagnosis"] = s.primary_diagnosis.map(icd_dot)
    log("spells", "ICD-10 format", (before != s.primary_diagnosis).sum(), "Codes without the dot (J189 for J18.9)",
        "Standardised to dotted form")
    n = s.duplicated().sum()
    s = s.drop_duplicates()
    log("spells", "Duplicate spells", n, "Same spell sent twice (resubmission), identical once formats are fixed", "Kept one")
    dup = s.spell_id.duplicated(keep=False)
    if dup.any():
        valid_tf0 = set(read("ref_treatment_function").treatment_function)
        bad = (~s.treatment_function.isin(valid_tf0)).astype(int) + (s.discharge_date < s.admission_date).astype(int) \
            + (s.discharge_date.dt.year < 1950).astype(int)
        s = s.assign(_bad=bad).sort_values(["spell_id", "_bad"])
        n = s.spell_id.duplicated().sum()
        s = s.drop_duplicates("spell_id").drop(columns="_bad")
        log("spells", "Conflicting duplicates", n, "Same spell sent twice with an error in one copy", "Kept the valid copy")
    assert not s.spell_id.duplicated().any()

    # recover invalid treatment function from the first consultant episode
    e = read("episodes")
    n = e.duplicated().sum()
    e = e.drop_duplicates()
    log("episodes", "Duplicate episodes", n, "Identical episode sent twice", "Kept one")
    first_tf = e[e.episode_order == "1"].set_index("spell_id").treatment_function
    valid_tf = set(read("ref_treatment_function").treatment_function)
    bad = ~s.treatment_function.isin(valid_tf)
    s.loc[bad, "treatment_function"] = s.loc[bad, "spell_id"].map(first_tf)
    log("spells", "Invalid treatment function", bad.sum(), "Code 999 is not a valid treatment function",
        "Taken from the spell's first consultant episode")

    # records that cannot be trusted
    reject = pd.Series("", index=s.index)
    reject[placeholder.reindex(s.index, fill_value=False)] = "Placeholder discharge date (1900-01-01)"
    reject[(reject == "") & (s.discharge_date < s.admission_date)] = "Discharge before admission"
    rejected = s[reject != ""].assign(reason=reject[reject != ""])
    why = {"Discharge before admission": "Discharge date earlier than admission date: one of them is wrong",
           "Placeholder discharge date (1900-01-01)": "Discharge date missing, filled with a default value"}
    for reason, g in rejected.groupby("reason"):
        log("spells", reason, len(g), why[reason], "Excluded; listed in rejected_spells.csv")
    s = s[reject == ""].copy()

    # derived fields used throughout the analysis
    s["los_days"] = (s.discharge_date - s.admission_date).dt.days.astype("Int64")
    log("spells", "Unfinished spells", s.discharge_date.isna().sum(), "Patient still in hospital when the extract was taken",
        "Kept with no discharge date; counted in bed occupancy, left out of length of stay")
    s["admission_group"] = s.admission_method.str[0].map({"1": "Elective", "2": "Emergency"})
    fy = s.admission_date.dt.year - (s.admission_date.dt.month < 4)
    s["financial_year"] = fy.astype(str) + "/" + (fy + 1).astype(str).str[-2:]
    s["age_band"] = pd.cut(s.age_on_admission.astype(int), [-1, 15, 44, 64, 74, 84, 200],
                           labels=["0-15", "16-44", "45-64", "65-74", "75-84", "85+"]).astype(str)
    for c in ("admission_date", "discharge_date"):
        s[c] = s[c].dt.strftime("%Y-%m-%d")
    log("spells", "Spells ready for analysis", len(s), "After fixes and exclusions", "Written to data/clean/spells.csv")

    keep = set(s.spell_id)
    e = e[e.spell_id.isin(keep)]
    d = read("diagnoses")
    before = d.icd10_code.copy()
    d["icd10_code"] = d.icd10_code.map(icd_dot)
    log("diagnoses", "ICD-10 format", (before != d.icd10_code).sum(), "Secondary codes without the dot", "Standardised")
    d = d[d.spell_id.isin(keep)]
    pr = read("procedures")
    pr = pr[pr.spell_id.isin(keep)]
    assert set(s.patient_id) <= set(p.patient_id), "every spell must link to a patient"

    tables = dict(patients=p, spells=s, episodes=e, diagnoses=d, procedures=pr, rejected_spells=rejected)
    for name in ("ref_icd10", "ref_opcs4", "ref_treatment_function", "ref_admission_method", "ref_discharge_destination",
                 "ref_discharge_method", "population", "ref_esp2013"):
        tables[name] = read(name)
    for name, df in tables.items():
        df.to_csv(os.path.join(OUT, f"{name}.csv"), index=False)
    pd.DataFrame(LOG).to_csv(os.path.join(OUT, "data_quality_log.csv"), index=False)
    print(pd.DataFrame(LOG).to_string())


if __name__ == "__main__":
    main()
