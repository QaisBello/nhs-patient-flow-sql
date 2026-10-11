"""pbikit: write a Power BI project (PBIP = TMDL semantic model + PBIR report) from a Python spec, and check it.

One file, no dependencies beyond jsonschema/referencing for validation. Each project keeps its own copy in
powerbi/tools/ and a spec.py that calls:

    build(spec)          -> writes <Name>.pbip, <Name>.SemanticModel/, <Name>.Report/, docs/measures.md, model.json
    validate(root)       -> checks every report file against Microsoft's JSON schemas and every reference in the model

Spec (a plain dict):
    name, root, base_url, base_desc
    tables:  {name: {file | m, description, columns: [(col, type, props)], added: [...], m_extra, m_last, filter, date_table}}
    measures: [(name, table, folder, format, dax, description)]
    relationships: [((from_table, from_col), (to_table, to_col), {extra tmdl props})]
    pages: [(key, display name, [visual, ...])]  -- visuals made with the helpers below

Lessons from testing in Power BI Desktop (all enforced or handled here):
  - names are case-insensitive: 'month' and 'Month' in one table fail on load (validate checks this)
  - format strings starting with a quote break TMDL: write R\\$#,0, not "R$"#,0
  - empty CSV cells must become null before a type change, or rows error on refresh
  - in DAX, BLANK() = FALSE() is TRUE: compare booleans with ==
"""
import glob
import json
import os
import re
import shutil
import textwrap
import uuid

SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"
INK, MUTED = "#13201B", "#6B7570"
M_TYPES = {"string": "type text", "int64": "Int64.Type", "decimal": "Currency.Type", "double": "type number",
           "dateTime": "type datetime", "boolean": "type logical"}
FORMAT = {"int64": "#,0", "decimal": "#,0.00", "double": "#,0.00"}


# ====================================================================== helpers
def uid(seed):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"pbikit/{seed}"))


def short(seed):
    return uid(seed).replace("-", "")[:20]


def q(name):
    """quote a TMDL name when it is not a plain identifier"""
    return name if name.replace("_", "").isalnum() and not name[0].isdigit() else "'" + name.replace("'", "''") + "'"


def ind(text, n):
    return textwrap.indent(textwrap.dedent(text).strip("\n"), "\t" * n)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def jwrite(path, obj):
    write(path, json.dumps(obj, indent=2) + "\n")


# ====================================================================== semantic model
def csv_m(t):
    cols = t["columns"]
    types = ",\n".join(f'{{"{c}", {M_TYPES[ty]}}}' for c, ty, _ in cols)
    filt = f'\n#"Filtered Rows" = Table.SelectRows(#"Changed Types", each [{t["filter"]}] = true),' if t.get("filter") else \
        '\n#"Filtered Rows" = #"Changed Types",'
    extra = textwrap.dedent(t.get("m_extra", "").strip("\n").rstrip()).strip("\n")
    last = t.get("m_last", "Filtered Rows")
    return f'''let
    Source = Csv.Document(
        Web.Contents(BaseUrl, [RelativePath = "{t['file']}"]),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    // empty cells and R's NA arrive as text and would fail the type change: make them null
    #"Blanks to Null" = Table.TransformColumns(#"Promoted Headers", {{}}, each if _ = "" or _ = "NA" then null else _),
    #"Changed Types" = Table.TransformColumnTypes(
        #"Blanks to Null",
        {{
{textwrap.indent(types, " " * 12)}
        }},
        "en-US"
    ),{textwrap.indent(filt, "    ")}{(chr(10) + textwrap.indent(extra, "    ") + ",") if extra else ""}
    Result = #"{last}"
in
    Result'''


def table_tmdl(name, t, measures):
    out = [f"/// {t['description']}", f"table {q(name)}"]
    if t.get("date_table"):
        out.append("\tdataCategory: Time")
    out.append("")
    for m, _tbl, folder, fmt, dax, desc in measures:
        out.append(f"\t/// {desc}")
        if "\n" in dax.strip():
            out.append(f"\tmeasure {q(m)} =")
            out.append(ind(dax, 3))
        else:
            out.append(f"\tmeasure {q(m)} = {dax.strip()}")
        out.append(f"\t\tformatString: {fmt}")
        out.append(f"\t\tdisplayFolder: {folder}")
        out.append("")
    for col, typ, extra in t["columns"] + t.get("added", []):
        out.append(f"\tcolumn {q(col)}")
        out.append(f"\t\tdataType: {typ}")
        if extra.get("isHidden"):
            out.append("\t\tisHidden")
        if extra.get("isKey"):
            out.append("\t\tisKey")
        fmt = extra.get("formatString", FORMAT.get(typ))
        if fmt:
            out.append(f"\t\tformatString: {fmt}")
        out.append(f"\t\tsummarizeBy: {extra.get('summarizeBy', 'none')}")
        out.append(f"\t\tsourceColumn: {col}")
        if extra.get("sortByColumn"):
            out.append(f"\t\tsortByColumn: {q(extra['sortByColumn'])}")
        if extra.get("dataCategory"):
            out.append(f"\t\tdataCategory: {extra['dataCategory']}")
        out.append("")
    m = textwrap.dedent(t["m"]).strip("\n") if t.get("m") else csv_m(t)
    out += [f"\tpartition {q(name)} = m", "\t\tmode: import", "\t\tsource = ```", textwrap.indent(m, "\t\t\t\t"), "\t\t\t\t```", ""]
    return "\n".join(out) + "\n"


def build_model(spec):
    root, name = spec["root"], spec["name"]
    sm = os.path.join(root, f"{name}.SemanticModel")
    shutil.rmtree(os.path.join(sm, "definition"), ignore_errors=True)
    jwrite(os.path.join(sm, "definition.pbism"), {"$schema": f"{SCHEMA}/item/semanticModel/definitionProperties/1.0.0/schema.json",
                                                  "version": "4.2", "settings": {"qnaEnabled": True}})
    d = os.path.join(sm, "definition")
    write(os.path.join(d, "database.tmdl"), "database\n\tcompatibilityLevel: 1601\n")
    refs = "\n".join(f"ref table {q(t)}" for t in spec["tables"])
    write(os.path.join(d, "model.tmdl"), f"""model Model
\tculture: en-GB
\tdefaultPowerBIDataSourceVersion: powerBI_V3
\tdiscourageImplicitMeasures
\tsourceQueryCulture: en-GB
\tdataAccessOptions
\t\tlegacyRedirects
\t\treturnErrorValuesAsNull

{refs}
""")
    write(os.path.join(d, "expressions.tmdl"),
          f'/// {spec["base_desc"]}\n'
          f'expression BaseUrl = "{spec["base_url"]}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n')
    rels = []
    for (ft, fc), (tt, tc), extra in spec["relationships"]:
        r = [f"relationship {uid(name + f'/{ft}.{fc}->{tt}.{tc}')}"]
        r += [f"\t{k}: {v}" for k, v in extra.items()]
        r += [f"\tfromColumn: {q(ft)}.{q(fc)}", f"\ttoColumn: {q(tt)}.{q(tc)}"]
        rels.append("\n".join(r))
    write(os.path.join(d, "relationships.tmdl"), "\n\n".join(rels) + "\n")
    for tname, t in spec["tables"].items():
        write(os.path.join(d, "tables", f"{tname}.tmdl"), table_tmdl(tname, t, [m for m in spec["measures"] if m[1] == tname]))


# ====================================================================== report helpers
def lit(v):
    if isinstance(v, bool):
        return {"expr": {"Literal": {"Value": "true" if v else "false"}}}
    if isinstance(v, (int, float)):
        return {"expr": {"Literal": {"Value": f"{v}D"}}}
    return {"expr": {"Literal": {"Value": "'" + str(v).replace("'", "''") + "'"}}}


def field(kind, table, prop):
    return {kind: {"Expression": {"SourceRef": {"Entity": table}}, "Property": prop}}


def proj(kind, table, prop, display=None):
    p = {"field": field(kind, table, prop), "queryRef": f"{table}.{prop}", "nativeQueryRef": prop}
    if display:
        p["displayName"] = display
    return p


def M(table, name, display=None):
    return proj("Measure", table, name, display)


def C(table, col, display=None):
    return proj("Column", table, col, display)


def color(c):
    return {"solid": {"color": lit(c)}}


def visual(page, key, vtype, x, y, w, h, roles, title_text=None, objects=None, sort=None, z=0, container=None):
    v = {"visualType": vtype, "query": {"queryState": {r: {"projections": p} for r, p in roles.items()}}, "drillFilterOtherVisuals": True}
    if sort:
        v["query"]["sortDefinition"] = {"sort": [{"field": sort[0]["field"], "direction": sort[1]}], "isDefaultSort": False}
    if objects:
        v["objects"] = objects
    vco = dict(container or {})
    if title_text:
        vco["title"] = [{"properties": {"show": lit(True), "text": lit(title_text), "fontSize": lit(12)}}]
    if vco:
        v["visualContainerObjects"] = vco
    name = short(f"{page}/{key}")
    return name, {"$schema": f"{SCHEMA}/item/report/definition/visualContainer/2.4.0/schema.json", "name": name,
                  "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z}, "visual": v}


def series_colors(projections, colors):
    """dataPoint fill per series of a line/column chart, matched by queryRef"""
    return [{"properties": {"fill": color(c)}, "selector": {"metadata": p["queryRef"]}} for p, c in zip(projections, colors)]


def card(page, key, x, y, w, h, measure_proj, size=24):
    return visual(page, key, "card", x, y, w, h, {"Values": [measure_proj]}, objects={
        "labels": [{"properties": {"fontSize": lit(size), "labelDisplayUnits": lit(1), "color": color(INK)}}],
        "categoryLabels": [{"properties": {"show": lit(True), "fontSize": lit(11)}}]}, z=x + y)


def text_box(page, key, x, y, w, h, text, size=18, bold=True):
    run = {"value": text, "textStyle": {"fontSize": f"{size}pt", "color": INK, **({"fontWeight": "bold"} if bold else {})}}
    name = short(f"{page}/{key}")
    return name, {"$schema": f"{SCHEMA}/item/report/definition/visualContainer/2.4.0/schema.json", "name": name,
                  "position": {"x": x, "y": y, "z": 0, "width": w, "height": h, "tabOrder": 0},
                  "visual": {"visualType": "textbox", "objects": {"general": [{"properties": {"paragraphs": [{"textRuns": [run]}]}}]}}}


def slicer(page, key, x, y, w, h, column_proj, title_text, single=False, mode="Dropdown"):
    objects = {"data": [{"properties": {"mode": lit(mode)}}]}
    if single:
        objects["selection"] = [{"properties": {"strictSingleSelect": lit(True)}}]
    return visual(page, key, "slicer", x, y, w, h, {"Values": [column_proj]}, title_text, objects=objects, z=900 + x)


def build_report(spec):
    root, name = spec["root"], spec["name"]
    rp = os.path.join(root, f"{name}.Report")
    shutil.rmtree(os.path.join(rp, "definition"), ignore_errors=True)
    jwrite(os.path.join(rp, "definition.pbir"), {"$schema": f"{SCHEMA}/item/report/definitionProperties/2.0.0/schema.json",
                                                 "version": "4.0", "datasetReference": {"byPath": {"path": f"../{name}.SemanticModel"}}})
    d = os.path.join(rp, "definition")
    jwrite(os.path.join(d, "version.json"), {"$schema": f"{SCHEMA}/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"})
    jwrite(os.path.join(d, "report.json"), {"$schema": f"{SCHEMA}/item/report/definition/report/3.0.0/schema.json", "themeCollection": {}})
    ps = spec["pages"]
    jwrite(os.path.join(d, "pages", "pages.json"), {"$schema": f"{SCHEMA}/item/report/definition/pagesMetadata/1.0.0/schema.json",
                                                    "pageOrder": [short(name + p) for p, _, _ in ps], "activePageName": short(name + ps[0][0])})
    for key, display, visuals in ps:
        names = [v for v, _ in visuals]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ValueError(f"page {key}: two visuals share a key (would overwrite each other): {dupes}")
        pid = short(name + key)
        jwrite(os.path.join(d, "pages", pid, "page.json"), {"$schema": f"{SCHEMA}/item/report/definition/page/2.0.0/schema.json",
                                                            "name": pid, "displayName": display, "displayOption": "FitToPage",
                                                            "height": 720, "width": 1280})
        for vname, v in visuals:
            jwrite(os.path.join(d, "pages", pid, "visuals", vname, "visual.json"), v)


def build(spec):
    root, name = spec["root"], spec["name"]
    build_model(spec)
    build_report(spec)
    jwrite(os.path.join(root, f"{name}.pbip"), {"$schema": f"{SCHEMA}/pbip/pbipProperties/1.0.0/schema.json", "version": "1.0",
                                                "artifacts": [{"report": {"path": f"{name}.Report"}}], "settings": {"enableAutoRecovery": True}})
    lines = ["# Measures", "", "Generated by `tools/spec.py`. Grouped by display folder.", ""]
    for m, tbl, folder, fmt, dax, desc in spec["measures"]:
        lines += [f"## {m}", "", f"*{folder}* · table `{tbl}` · format `{fmt}` · {desc}", "", "```dax", f"{m} =", textwrap.dedent(dax).strip(), "```", ""]
    write(os.path.join(root, "docs", "measures.md"), "\n".join(lines))
    tables = [dict(name=t, description=d["description"], columns=[dict(name=c, type=ty, hidden=bool(x.get("isHidden")), key=bool(x.get("isKey")))
                                                                  for c, ty, x in d["columns"] + d.get("added", [])]) for t, d in spec["tables"].items()]
    rels = [dict(fromTable=a[0], fromColumn=a[1], toTable=b[0], toColumn=b[1], both=x.get("crossFilteringBehavior") == "bothDirections")
            for a, b, x in spec["relationships"]]
    meas = [dict(name=m, table=t, folder=f, format=fmt, dax=textwrap.dedent(dax).strip(), description=desc) for m, t, f, fmt, dax, desc in spec["measures"]]
    pages = [dict(page=title, visuals=[dict(type=v["visual"]["visualType"], **{k: v["position"][k] for k in ("x", "y", "width", "height")}) for _, v in vs])
             for _, title, vs in spec["pages"]]
    jwrite(os.path.join(root, "model.json"), dict(tables=tables, relationships=rels, measures=meas, pages=pages, base_url=spec["base_url"]))
    print(f"generated {name}: {len(spec['tables'])} tables, {len(spec['measures'])} measures, "
          f"{sum(len(v) for _, _, v in spec['pages'])} visuals on {len(spec['pages'])} pages")


# ====================================================================== validation
def validate(root):
    from jsonschema import Draft7Validator
    from referencing import Registry, Resource
    import urllib.request

    cache = os.path.join(root, "tools", ".schemas")
    raw = "https://raw.githubusercontent.com/microsoft/json-schemas/main/fabric/"
    prefix = SCHEMA + "/"
    problems = []

    def fetch(uri):
        rel = uri.split("#")[0].replace(prefix, "")
        path = os.path.join(cache, rel)
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            urllib.request.urlretrieve(raw + rel, path)
        return json.load(open(path, encoding="utf-8"))

    registry = Registry(retrieve=lambda uri: Resource.from_contents(fetch(uri)))
    files = [f for pat in ("*.Report/**/*.json", "*.Report/*.pbir", "*.SemanticModel/*.pbism", "*.pbip")
             for f in glob.glob(os.path.join(root, pat), recursive=True)]
    for f in sorted(set(files)):
        doc = json.load(open(f, encoding="utf-8"))
        uri = doc.get("$schema")
        if not uri:
            problems.append(f"{f}: no $schema")
            continue
        schema = fetch(uri)
        v = Draft7Validator(schema, registry=registry.with_resource(uri, Resource.from_contents(schema)))
        for e in v.iter_errors(doc):
            problems.append(f"{os.path.relpath(f, root)}: {'/'.join(map(str, e.absolute_path))}: {e.message[:200]}")

    model = {}
    for f in glob.glob(os.path.join(root, "*.SemanticModel", "definition", "tables", "*.tmdl")):
        text = open(f, encoding="utf-8").read()
        head = text.split("source = ```")[0]
        if re.search(r"^ +[a-z/]", head, re.M):
            problems.append(f"{os.path.basename(f)}: spaces used for indentation outside the M expression")
        if re.search(r"^\t\tformatString: \"", head, re.M):
            problems.append(f"{os.path.basename(f)}: a formatString starts with a quote (escape with backslash instead)")
        tname = re.search(r"^table (.+)$", text, re.M).group(1).strip("'")
        cols = {m.strip("'") for m in re.findall(r"^\tcolumn (.+)$", text, re.M)}
        meas = {m.group(1).strip("'"): m.group(2) for m in re.finditer(r"^\tmeasure (.+?) =(.*?)(?=^\t\tformatString)", text, re.M | re.S)}
        sorts = [s.strip("'") for s in re.findall(r"sortByColumn: (.+)$", text, re.M)]
        keys = re.findall(r"^\tcolumn (.+)\n(?:\t\t.*\n)*?\t\tisKey", text, re.M)
        model[tname] = dict(columns=cols, measures=meas, sorts=sorts, keys=keys, date="dataCategory: Time" in head)
    seen = {}
    for t, d in model.items():
        names = [c.lower() for c in d["columns"]] + [m.lower() for m in d["measures"]]
        for n in {x for x in names if names.count(x) > 1}:
            problems.append(f"{t}: name '{n}' is used more than once (names are case-insensitive)")
        for m in d["measures"]:
            if m.lower() in seen:
                problems.append(f"measure {m} on {t} clashes with {seen[m.lower()]}")
            seen[m.lower()] = f"measure on {t}"
            if m.lower() in {x.lower() for x in model}:
                problems.append(f"measure {m} has the same name as a table")
        for s in d["sorts"]:
            if s not in d["columns"]:
                problems.append(f"{t}: sortByColumn {s} is not a column")
        if d["date"] and not d["keys"]:
            problems.append(f"{t}: date table has no key column")
    all_measures = {m for d in model.values() for m in d["measures"]}
    lower_tables = {t.lower(): t for t in model}
    for t, d in model.items():
        for m, dax in d["measures"].items():
            body = re.sub(r'"[^"]*"', '""', dax)                                   # ignore string literals
            refs = [(a or c, b or d_) for a, b, c, d_ in re.findall(r"'([^']+)'\[([^\]]+)\]|\b([A-Za-z_][\w]*)\[([^\]]+)\]", body)]
            for tbl, col in refs:
                if tbl in model:
                    if col not in model[tbl]["columns"] and col not in model[tbl]["measures"]:
                        problems.append(f"measure {m}: {tbl}[{col}] is not a column")
                elif tbl.lower() not in lower_tables and not tbl.isupper():
                    problems.append(f"measure {m}: table {tbl} not in model")
            stripped = re.sub(r"'[^']+'\[[^\]]+\]|\b[A-Za-z_]\w*\[[^\]]+\]", "", body)
            for ref in re.findall(r"\[([^\]]+)\]", stripped):
                if ref.startswith("@"):
                    continue                                                       # ADDCOLUMNS helper column
                if ref not in all_measures:
                    problems.append(f"measure {m}: [{ref}] is not a measure")
                if ref == m:
                    problems.append(f"measure {m}: refers to itself")
    relf = glob.glob(os.path.join(root, "*.SemanticModel", "definition", "relationships.tmdl"))
    for side in re.findall(r"(?:fromColumn|toColumn): (.+)$", open(relf[0]).read(), re.M) if relf else []:
        mm = re.match(r"('?)(.+?)\1\.('?)(.+?)\3$", side.strip())
        if mm.group(2) not in model or mm.group(4) not in model[mm.group(2)]["columns"]:
            problems.append(f"relationship column {side} not found")
    nv = 0
    for f in glob.glob(os.path.join(root, "*.Report", "definition", "pages", "*", "visuals", "*", "visual.json")):
        v = json.load(open(f))
        nv += 1

        def walk(o):
            if isinstance(o, dict):
                for kind in ("Column", "Measure"):
                    if kind in o and isinstance(o[kind], dict) and "Property" in o[kind]:
                        t, p = o[kind]["Expression"]["SourceRef"]["Entity"], o[kind]["Property"]
                        if t not in model or p not in model[t]["columns" if kind == "Column" else "measures"]:
                            problems.append(f"{v['visual']['visualType']} {v['name']}: {kind} {t}.{p} not in model")
                for x in o.values():
                    walk(x)
            elif isinstance(o, list):
                for x in o:
                    walk(x)
        walk(v)
    print(f"{len(files)} JSON files checked against Microsoft schemas, {len(model)} tables, {len(all_measures)} measures, {nv} visuals")
    for p in problems:
        print("PROBLEM:", p)
    return problems
