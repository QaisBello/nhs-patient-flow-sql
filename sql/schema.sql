-- Schema for the cleaned extract (data/clean). Loaded by src/run_all.py and by the web page.
CREATE TABLE patients (patient_id TEXT PRIMARY KEY, sex TEXT, birth_month TEXT, ethnic_category TEXT,
                       imd_decile INTEGER, gp_practice_code TEXT);
CREATE TABLE spells (spell_id TEXT PRIMARY KEY, patient_id TEXT REFERENCES patients, provider_code TEXT,
                     admission_date TEXT, discharge_date TEXT, admission_method TEXT, treatment_function TEXT,
                     primary_diagnosis TEXT, discharge_method TEXT, discharge_destination TEXT,
                     age_on_admission INTEGER, los_days INTEGER, admission_group TEXT, financial_year TEXT, age_band TEXT);
CREATE TABLE episodes (episode_id TEXT PRIMARY KEY, spell_id TEXT REFERENCES spells, episode_order INTEGER,
                       treatment_function TEXT, episode_start TEXT, episode_end TEXT, consultant_code TEXT);
CREATE TABLE diagnoses (spell_id TEXT REFERENCES spells, position INTEGER, icd10_code TEXT);
CREATE TABLE procedures (spell_id TEXT REFERENCES spells, position INTEGER, opcs4_code TEXT, procedure_date TEXT);
CREATE TABLE ref_icd10 (icd10_code TEXT PRIMARY KEY, description TEXT);
CREATE TABLE ref_opcs4 (opcs4_code TEXT PRIMARY KEY, description TEXT);
CREATE TABLE ref_treatment_function (treatment_function TEXT PRIMARY KEY, description TEXT);
CREATE TABLE ref_admission_method (admission_method TEXT PRIMARY KEY, description TEXT, admission_group TEXT);
CREATE TABLE ref_discharge_destination (discharge_destination TEXT PRIMARY KEY, description TEXT);
CREATE TABLE ref_discharge_method (discharge_method TEXT PRIMARY KEY, description TEXT);
CREATE TABLE population (age_band TEXT, sex TEXT, imd_quintile INTEGER, population INTEGER);
CREATE TABLE ref_esp2013 (age_band TEXT PRIMARY KEY, esp2013_weight INTEGER);
CREATE INDEX ix_spells_patient ON spells (patient_id, admission_date);
CREATE INDEX ix_spells_dates ON spells (admission_date, discharge_date);
CREATE INDEX ix_dx_spell ON diagnoses (spell_id, icd10_code);
