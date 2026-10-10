import os
import re
import subprocess
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN = os.path.join(ROOT, "data", "clean")
RAW = os.path.join(ROOT, "data", "raw")


def clean(name):
    return pd.read_csv(os.path.join(CLEAN, f"{name}.csv"), dtype=str, keep_default_na=False, na_values=[""])


def test_raw_extract_really_is_messy():
    raw = pd.read_csv(os.path.join(RAW, "spells.csv"), dtype=str, keep_default_na=False)
    assert raw.spell_id.duplicated().any()                         # resubmissions
    assert raw.admission_date.str.contains("/").any()              # DD/MM/YYYY dates
    assert (~raw.primary_diagnosis.str.contains(r"\.") & (raw.primary_diagnosis.str.len() > 3)).any()   # J189


def test_spells_are_unique_valid_and_linked():
    s, p = clean("spells"), clean("patients")
    assert not s.spell_id.duplicated().any()
    assert not p.patient_id.duplicated().any()
    assert set(s.patient_id) <= set(p.patient_id)
    assert s.admission_date.str.fullmatch(r"\d{4}-\d{2}-\d{2}").all()
    done = s[s.discharge_date.notna()]
    assert (done.discharge_date >= done.admission_date).all()
    assert set(s.treatment_function) <= set(clean("ref_treatment_function").treatment_function)
    assert s.primary_diagnosis.str.fullmatch(r"[A-Z]\d{2}(\.\d)?").all()


def test_every_raw_spell_is_accounted_for():
    raw = pd.read_csv(os.path.join(RAW, "spells.csv"), dtype=str)
    kept, rejected = clean("spells"), clean("rejected_spells")
    assert raw.spell_id.nunique() == len(kept) + len(rejected)
    assert not set(kept.spell_id) & set(rejected.spell_id)


def test_unfinished_spells_have_no_length_of_stay():
    s = clean("spells")
    open_spells = s[s.discharge_date.isna()]
    assert len(open_spells) > 0 and open_spells.los_days.isna().all()


def test_quality_log_records_each_fix():
    log = clean("data_quality_log")
    for check in ("Duplicate spells", "Date format", "ICD-10 format", "Invalid treatment function",
                  "Discharge before admission", "Unfinished spells"):
        assert check in set(log.check), check


def test_sql_answers_match():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "src", "run_all.py")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.count("PASS") == 12
