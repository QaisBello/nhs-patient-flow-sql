"""Power BI version of the patient flow project: a trust activity, beds and inequalities pack. Run from powerbi/:

    python tools/spec.py        # writes Patient_Flow.pbip and its folders
    python tools/validate.py    # schema and reference checks
    python tools/expected.py    # what the visuals should show, checked against the SQL answers (answers/expected.json)

The same definitions as the SQL (sql/q*.sql): midnight bed occupancy against 170 beds from June 2024, 30-day emergency
readmissions flagged in Power Query, discharges by weekday through an inactive relationship (USERELATIONSHIP), and
emergency admission rates directly age-standardised to the 2013 European Standard Population in DAX.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pbikit import C, M, build, card, color, lit, series_colors, slicer, text_box, visual  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "Patient_Flow"
TEAL, ORANGE, GREY, BLUE, INK, PINK = "#0F766E", "#C2410C", "#9AA3A0", "#2443D6", "#13201B", "#C2367A"
BEDS = 170

AGE_BAND = '''if [age_on_admission] = null then null else if [age_on_admission] >= 90 then "90+"
                else Text.From(Number.IntegerDivide([age_on_admission], 5) * 5) & "-" & Text.From(Number.IntegerDivide([age_on_admission], 5) * 5 + 4)'''

TABLES = {
    "Spells": dict(
        file="spells.csv",
        description="One row per hospital stay (cleaned; rejected spells excluded). Readmission flags are added in Power Query "
                    "with the SQL's rules (sql/q06.sql).",
        columns=[("spell_id", "string", {"isKey": True, "isHidden": True}), ("patient_id", "string", {"isHidden": True}),
                 ("provider_code", "string", {"isHidden": True}), ("admission_date", "dateTime", {"formatString": "dd mmm yyyy"}),
                 ("discharge_date", "dateTime", {"formatString": "dd mmm yyyy"}), ("admission_method", "string", {}),
                 ("treatment_function", "string", {"isHidden": True}), ("primary_diagnosis", "string", {}),
                 ("discharge_method", "string", {}), ("discharge_destination", "string", {}), ("age_on_admission", "int64", {}),
                 ("los_days", "int64", {}), ("admission_group", "string", {}), ("financial_year", "string", {}), ("age_band", "string", {})],
        added=[("Age Band 5y", "string", {"isHidden": True}), ("Is Index Spell", "int64", {"isHidden": True}),
               ("Readmitted 30d", "int64", {"isHidden": True})],
        m_extra=f'''
            #"Age Band 5y" = Table.AddColumn(#"Filtered Rows", "Age Band 5y", each {AGE_BAND}, type text),
            Emergency = Table.Buffer(Table.RenameColumns(
                Table.SelectColumns(Table.SelectRows(#"Age Band 5y", each [admission_group] = "Emergency"), {{"patient_id", "spell_id", "admission_date"}}),
                {{{{"patient_id", "r_patient"}}, {{"spell_id", "r_spell"}}, {{"admission_date", "r_admitted"}}}})),
            Joined = Table.NestedJoin(#"Age Band 5y", {{"patient_id"}}, Emergency, {{"r_patient"}}, "Later", JoinKind.LeftOuter),
            // index spell: discharged alive, not transferred to another hospital, with a full 30 days of follow-up (as sql/q06.sql)
            #"Is Index Spell" = Table.AddColumn(Joined, "Is Index Spell", each
                if [discharge_date] <> null and [discharge_method] <> "4" and [discharge_destination] <> "51"
                   and [discharge_date] <= #datetime(2026, 3, 1, 0, 0, 0) then 1 else 0, Int64.Type),
            #"Readmitted 30d" = Table.AddColumn(#"Is Index Spell", "Readmitted 30d", each
                if [Is Index Spell] = 0 then null
                else if Table.RowCount(Table.SelectRows([Later], (r) => r[r_spell] <> [spell_id]
                        and r[r_admitted] >= [discharge_date] and r[r_admitted] <= Date.AddDays([discharge_date], 30))) > 0 then 1 else 0,
                Int64.Type),
            #"Without Join" = Table.RemoveColumns(#"Readmitted 30d", {{"Later"}})
        ''', m_last="Without Join"),
    "Patients": dict(
        file="patients.csv", description="One row per patient: sex, ethnicity and deprivation (IMD decile, 1 = most deprived).",
        columns=[("patient_id", "string", {"isKey": True, "isHidden": True}), ("sex", "string", {}), ("birth_month", "string", {"isHidden": True}),
                 ("ethnic_category", "string", {}), ("imd_decile", "int64", {}), ("gp_practice_code", "string", {"isHidden": True})],
        added=[("imd_quintile", "int64", {"isHidden": True})],
        m_extra='''
            #"imd_quintile" = Table.AddColumn(#"Filtered Rows", "imd_quintile", each
                if [imd_decile] = null then null else Number.IntegerDivide([imd_decile] + 1, 2), Int64.Type)
        ''', m_last="imd_quintile"),
    "Deprivation": dict(
        description="Deprivation quintiles: 1 = most deprived fifth of areas, 5 = least deprived.",
        m='''
let
    Source = Table.FromRecords({
        [imd_quintile = 1, Quintile = "1 (most deprived)"], [imd_quintile = 2, Quintile = "2"], [imd_quintile = 3, Quintile = "3"],
        [imd_quintile = 4, Quintile = "4"], [imd_quintile = 5, Quintile = "5 (least deprived)"]}),
    Result = Table.TransformColumnTypes(Source, {{"imd_quintile", Int64.Type}, {"Quintile", type text}})
in
    Result''',
        columns=[("imd_quintile", "int64", {"isKey": True, "isHidden": True}), ("Quintile", "string", {"sortByColumn": "imd_quintile"})]),
    "Age Bands": dict(
        file="ref_esp2013.csv", description="Five-year age bands with 2013 European Standard Population weights (for age standardisation).",
        columns=[("age_band", "string", {"isKey": True}), ("esp2013_weight", "int64", {"isHidden": True})],
        added=[("Band Order", "int64", {"isHidden": True})],
        m_extra='''
            #"Band Order" = Table.AddColumn(#"Filtered Rows", "Band Order", each
                if [age_band] = "90+" then 90 else Number.FromText(Text.BeforeDelimiter([age_band], "-")), Int64.Type)
        ''', m_last="Band Order"),
    "Population": dict(
        file="population.csv", description="Catchment population by five-year age band, sex and deprivation quintile (denominators for rates).",
        columns=[("age_band", "string", {"isHidden": True}), ("sex", "string", {"isHidden": True}),
                 ("imd_quintile", "int64", {"isHidden": True}), ("population", "int64", {})]),
    "Specialty": dict(
        file="ref_treatment_function.csv", description="Treatment function codes (NHS Data Dictionary).",
        columns=[("treatment_function", "string", {"isKey": True, "isHidden": True}), ("description", "string", {})]),
    "Date": dict(
        date_table=True,
        description="Every day from 1 April 2024 to 31 March 2026. Occupancy Counted = 1 from 1 June 2024: patients admitted before "
                    "the extract began are missing, so earlier nights undercount (as sql/q04.sql).",
        m='''
let
    Days = List.Dates(#date(2024, 4, 1), Duration.Days(#date(2026, 3, 31) - #date(2024, 4, 1)) + 1, #duration(1, 0, 0, 0)),
    Base = Table.FromList(Days, Splitter.SplitByNothing(), {"d"}),
    Dated = Table.AddColumn(Base, "Date", each DateTime.From([d]), type datetime),
    MonthStart = Table.AddColumn(Dated, "Month Start", each DateTime.From(Date.StartOfMonth([d])), type datetime),
    MonthName = Table.AddColumn(MonthStart, "Month", each Date.ToText([d], "MMM yyyy", "en-GB"), type text),
    FY = Table.AddColumn(MonthName, "Financial Year", each
        let y = if Date.Month([d]) >= 4 then Date.Year([d]) else Date.Year([d]) - 1 in Text.From(y) & "/" & Text.End(Text.From(y + 1), 2), type text),
    Weekday = Table.AddColumn(FY, "Weekday", each Date.ToText([d], "ddd", "en-GB"), type text),
    WeekdayNo = Table.AddColumn(Weekday, "Weekday No", each Date.DayOfWeek([d], Day.Monday) + 1, Int64.Type),
    Counted = Table.AddColumn(WeekdayNo, "Occupancy Counted", each if [d] >= #date(2024, 6, 1) then 1 else 0, Int64.Type),
    Result = Table.RemoveColumns(Counted, {"d"})
in
    Result''',
        columns=[("Date", "dateTime", {"isKey": True, "formatString": "dd mmm yyyy"}), ("Month Start", "dateTime", {"formatString": "mmm yyyy"}),
                 ("Month", "string", {"sortByColumn": "Month Start"}), ("Financial Year", "string", {}),
                 ("Weekday", "string", {"sortByColumn": "Weekday No"}), ("Weekday No", "int64", {"isHidden": True}),
                 ("Occupancy Counted", "int64", {"isHidden": True})]),
}

RELATIONSHIPS = [
    (("Spells", "admission_date"), ("Date", "Date"), {}),
    (("Spells", "discharge_date"), ("Date", "Date"), {"isActive": "false"}),
    (("Spells", "patient_id"), ("Patients", "patient_id"), {}),
    (("Spells", "treatment_function"), ("Specialty", "treatment_function"), {}),
    (("Spells", "Age Band 5y"), ("Age Bands", "age_band"), {}),
    (("Patients", "imd_quintile"), ("Deprivation", "imd_quintile"), {}),
    (("Population", "imd_quintile"), ("Deprivation", "imd_quintile"), {}),
    (("Population", "age_band"), ("Age Bands", "age_band"), {}),
]

S = "Spells"
MEASURES = [
    ("Spells Count", S, "Activity", "#,0", "COUNTROWS ( Spells )", "Hospital stays (spells), counted on admission date."),
    ("Emergency Admissions", S, "Activity", "#,0", 'CALCULATE ( [Spells Count], Spells[admission_group] = "Emergency" )', "Emergency spells."),
    ("Elective Admissions", S, "Activity", "#,0", 'CALCULATE ( [Spells Count], Spells[admission_group] = "Elective" )', "Elective spells."),
    ("Mean Length of Stay", S, "Length of stay", "0.0", "CALCULATE ( AVERAGE ( Spells[los_days] ), NOT ISBLANK ( Spells[discharge_date] ) )",
     "Mean days in hospital, discharged spells."),
    ("Median Length of Stay", S, "Length of stay", "0.0", "CALCULATE ( MEDIAN ( Spells[los_days] ), NOT ISBLANK ( Spells[discharge_date] ) )",
     "Median days in hospital, discharged spells."),
    ("Overnight Discharges", S, "Flow", "#,0",
     "CALCULATE ( [Spells Count], USERELATIONSHIP ( Spells[discharge_date], 'Date'[Date] ), Spells[los_days] > 0 )",
     "Overnight stays counted on their discharge date instead of admission date (the inactive relationship), as sql/q08.sql."),
    ("Discharges per Day", S, "Flow", "0.0", "DIVIDE ( [Overnight Discharges], COUNTROWS ( 'Date' ) )", "Average discharges per calendar day in context."),
    ("Bed Base", S, "Beds", "#,0", f"{BEDS}", "General and acute beds, as in the SQL."),
    ("Beds Occupied at Midnight", S, "Beds", "#,0", """VAR _d = MAX ( 'Date'[Date] )
RETURN
    CALCULATE (
        [Spells Count],
        REMOVEFILTERS ( 'Date' ),
        Spells[admission_date] <= _d,
        ISBLANK ( Spells[discharge_date] ) || Spells[discharge_date] > _d
    )""", "Patients in a bed at midnight on the last day in context: admitted on or before it and not yet discharged."),
    ("Average Beds Occupied", S, "Beds", "0.0", """AVERAGEX (
    CALCULATETABLE ( VALUES ( 'Date'[Date] ), 'Date'[Occupancy Counted] = 1 ),
    [Beds Occupied at Midnight]
)""", "Average of the nightly counts, from June 2024."),
    ("Bed Occupancy", S, "Beds", "0.0%", "DIVIDE ( [Average Beds Occupied], [Bed Base] )", "Average midnight occupancy against the bed base."),
    ("Peak Beds Occupied", S, "Beds", "#,0", """MAXX (
    CALCULATETABLE ( VALUES ( 'Date'[Date] ), 'Date'[Occupancy Counted] = 1 ),
    [Beds Occupied at Midnight]
)""", "Fullest night in context."),
    ("Nights Over 95%", S, "Beds", "#,0", """COUNTROWS (
    FILTER (
        CALCULATETABLE ( VALUES ( 'Date'[Date] ), 'Date'[Occupancy Counted] = 1 ),
        [Beds Occupied at Midnight] > 0.95 * [Bed Base]
    )
)""", "Nights above 95% occupancy, the level at which flow suffers."),
    ("95% Line", S, "Beds", "0%", "0.95", "Reference line for charts."),
    ("Readmission Rate (30 days)", S, "Readmissions", "0.0%", "DIVIDE ( SUM ( Spells[Readmitted 30d] ), SUM ( Spells[Is Index Spell] ) )",
     "Index spells followed by an emergency admission within 30 days of discharge."),
    ("Emergency Admissions per Year", S, "Inequalities", "#,0.0",
     'DIVIDE ( [Emergency Admissions], CALCULATE ( DISTINCTCOUNT ( \'Date\'[Financial Year] ), REMOVEFILTERS ( \'Date\' ) ) )',
     "Emergency admissions divided by the years of data (2)."),
    ("Population Count", S, "Inequalities", "#,0", "SUM ( Population[population] )", "Catchment population in context."),
    ("Crude Rate per 1,000", S, "Inequalities", "0.0",
     "DIVIDE ( 1000 * CALCULATE ( [Emergency Admissions per Year], NOT ISBLANK ( Patients[imd_quintile] ) ), [Population Count] )",
     "Emergency admissions per 1,000 population a year, not adjusted for age."),
    ("Age-Standardised Rate per 1,000", S, "Inequalities", "0.0", """VAR _bands =
    ADDCOLUMNS (
        VALUES ( 'Age Bands'[age_band] ),
        "@w", CALCULATE ( MAX ( 'Age Bands'[esp2013_weight] ) ),
        "@pop", [Population Count],
        "@events", CALCULATE ( [Emergency Admissions per Year], NOT ISBLANK ( Patients[imd_quintile] ) )
    )
VAR _rated = FILTER ( _bands, [@pop] > 0 )
RETURN
    DIVIDE ( SUMX ( _rated, DIVIDE ( 1000 * [@events], [@pop] ) * [@w] ), SUMX ( _rated, [@w] ) )""",
     "Directly age-standardised to the 2013 European Standard Population: band rates weighted by ESP and averaged."),
    ("Deprivation Gap", S, "Inequalities", '0.0"x"', """DIVIDE (
    CALCULATE ( [Age-Standardised Rate per 1,000], Deprivation[imd_quintile] = 1 ),
    CALCULATE ( [Age-Standardised Rate per 1,000], Deprivation[imd_quintile] = 5 )
)""", "Most deprived fifth against least deprived fifth, age-standardised."),
]

# ---------------------------------------------------------------- report
p1, p2, p3 = "activity", "beds", "inequalities"
emg, ele = M(S, "Emergency Admissions", "Emergency"), M(S, "Elective Admissions", "Elective")
occ, line95 = M(S, "Bed Occupancy", "Occupancy"), M(S, "95% Line", "95%")
asr, crude = M(S, "Age-Standardised Rate per 1,000", "Age-standardised"), M(S, "Crude Rate per 1,000", "Crude")
PAGES = [
    (p1, "Activity", [
        text_box(p1, "title", 24, 12, 860, 52, "Admitted patient care, April 2024 to March 2026 (synthetic trust)", 18),
        slicer(p1, "fy", 1000, 8, 256, 64, C("Date", "Financial Year", "Financial year"), None),
        card(p1, "em", 24, 76, 236, 96, M(S, "Emergency Admissions", "Emergency admissions")),
        card(p1, "el", 272, 76, 236, 96, M(S, "Elective Admissions", "Elective admissions")),
        card(p1, "los", 520, 76, 236, 96, M(S, "Mean Length of Stay", "Mean length of stay (days)")),
        card(p1, "readm", 768, 76, 236, 96, M(S, "Readmission Rate (30 days)", "Emergency readmission in 30 days (all stays)")),
        card(p1, "occ", 1016, 76, 240, 96, M(S, "Bed Occupancy", "Bed occupancy (from Jun 2024)")),
        visual(p1, "monthly", "lineChart", 24, 184, 800, 260, {"Category": [C("Date", "Month Start", "Month")], "Y": [emg, ele]},
               "Admissions by month", objects={"dataPoint": series_colors([emg, ele], [ORANGE, TEAL])}, z=10),
        visual(p1, "weekday", "clusteredColumnChart", 840, 184, 416, 260,
               {"Category": [C("Date", "Weekday")], "Y": [M(S, "Discharges per Day", "Discharges a day")]},
               "Discharges by weekday (inactive relationship)", objects={"dataPoint": [{"properties": {"fill": color(TEAL)}}],
                                                                           "labels": [{"properties": {"show": lit(True)}}]},
               sort=(C("Date", "Weekday"), "Ascending"), z=11),
        visual(p1, "specialty", "tableEx", 24, 456, 1232, 252,
               {"Values": [C("Specialty", "description", "Specialty"), M(S, "Spells Count", "Spells"), M(S, "Emergency Admissions", "Emergency"),
                           M(S, "Mean Length of Stay", "Mean LoS"), M(S, "Median Length of Stay", "Median LoS"),
                           M(S, "Readmission Rate (30 days)", "Readmitted in 30 days")]},
               "By specialty", sort=(M(S, "Spells Count"), "Descending"), z=12),
    ]),
    (p2, "Beds", [
        text_box(p2, "title", 24, 12, 1000, 52, "Midnight bed occupancy against a 170-bed general and acute base", 18),
        card(p2, "avg", 24, 76, 300, 96, M(S, "Average Beds Occupied", "Average beds occupied")),
        card(p2, "peak", 336, 76, 300, 96, M(S, "Peak Beds Occupied", "Fullest night")),
        card(p2, "n95", 648, 76, 300, 96, M(S, "Nights Over 95%", "Nights over 95%")),
        card(p2, "occ", 960, 76, 296, 96, M(S, "Bed Occupancy", "Average occupancy")),
        visual(p2, "monthly", "lineChart", 24, 184, 1232, 250, {"Category": [C("Date", "Month Start", "Month")], "Y": [occ, line95]},
               "Average occupancy by month", objects={"dataPoint": series_colors([occ, line95], [TEAL, ORANGE])}, z=10),
        visual(p2, "nightly", "lineChart", 24, 446, 1232, 262,
               {"Category": [C("Date", "Date")], "Y": [M(S, "Beds Occupied at Midnight", "Beds occupied")]},
               "Every night (the first two months undercount: patients admitted before April 2024 are not in the extract)",
               objects={"dataPoint": [{"properties": {"fill": color(INK)}}]}, z=11),
    ]),
    (p3, "Inequalities", [
        text_box(p3, "title", 24, 12, 1100, 52, "Emergency admissions by deprivation, age-standardised in DAX", 18),
        card(p3, "gap", 24, 76, 300, 96, M(S, "Deprivation Gap", "Most vs least deprived fifth")),
        visual(p3, "rates", "clusteredColumnChart", 24, 184, 720, 524, {"Category": [C("Deprivation", "Quintile", "Deprivation quintile")],
                                                                          "Y": [asr, crude]},
               "Emergency admissions per 1,000 a year", objects={"dataPoint": series_colors([asr, crude], [PINK, GREY]),
                                                                  "labels": [{"properties": {"show": lit(True)}}]},
               sort=(C("Deprivation", "Quintile"), "Ascending"), z=10),
        visual(p3, "table", "tableEx", 760, 184, 496, 524,
               {"Values": [C("Deprivation", "Quintile"), M(S, "Population Count", "Population"),
                           M(S, "Emergency Admissions per Year", "Admissions a year"), M(S, "Crude Rate per 1,000", "Crude"),
                           M(S, "Age-Standardised Rate per 1,000", "Age-standardised")]},
               "Rates by quintile (patients with no deprivation decile excluded)", sort=(C("Deprivation", "Quintile"), "Ascending"), z=11),
    ]),
]

SPEC = dict(name=NAME, root=ROOT, tables=TABLES, measures=MEASURES, relationships=RELATIONSHIPS, pages=PAGES,
            base_url="https://raw.githubusercontent.com/QaisBello/nhs-patient-flow-sql/main/data/clean/",
            base_desc="Folder of cleaned CSVs from this repo (data/clean). Point it at a local folder or another branch to test.")

if __name__ == "__main__":
    build(SPEC)
