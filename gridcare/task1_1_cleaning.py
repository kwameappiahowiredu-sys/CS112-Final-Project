import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
RAW = BASE / "data" / "raw"
CLEAN = BASE / "data" / "clean"
REPORTS = BASE / "reports"

MISSING_TOKENS = ["\\N", "NULL", "null", "None", "NA", "N/A", "n/a", "-", "", " "]

VALID_VOLTAGES = [11, 33, 69, 161, 330]
LAT_RANGE = (3.0, 16.0)
LON_RANGE = (-18.0, 5.0)
YEAR_RANGE = (1900, datetime.now().year)

UTILITY_TYPES = ["Generation", "Transmission", "Distribution"]
UTILITY_ACTIVE = ["Y", "N"]
SUBSTATION_TYPES = ["Distribution", "Bulk Supply Point", "Transmission"]
SUBSTATION_STATUS = ["Active", "Inactive"]
LINE_STATUS = ["Active", "Under Maintenance"]
LINE_TYPES = ["Overhead", "Underground"]

COUNTRY_CANONICAL = {
    "ghana": "Ghana",
    "togo": "Togo",
    "benin": "Benin",
    "guinea": "Guinea",
    "cote": "Cote d'Ivoire",
    "cote d'ivoire": "Cote d'Ivoire",
    "burkina": "Burkina Faso",
    "burkina faso": "Burkina Faso",
    "togo/benin": "Togo/Benin",
}

transformations = []
issues = []


def log_transformation(dataset, step, detail):
    transformations.append({"dataset": dataset, "step": step, "detail": detail})


def log_issue(dataset, severity, issue, count, action):
    issues.append({
        "dataset": dataset,
        "severity": severity,
        "issue": issue,
        "count": int(count),
        "action": action,
    })


def load_raw():
    utilities = pd.read_csv(RAW / "utilities.csv")
    substations = pd.read_csv(RAW / "substations.csv")
    lines = pd.read_csv(RAW / "lines.csv")
    return utilities, substations, lines


def strip_text(df, dataset):
    changed = 0
    for col in df.columns:
        if df[col].dtype == object:
            before = df[col].copy()
            df[col] = df[col].apply(lambda v: v.strip() if isinstance(v, str) else v)
            changed += int((before.fillna("") != df[col].fillna("")).sum())
    if changed:
        log_transformation(dataset, "whitespace", f"stripped leading/trailing whitespace in {changed} cells")
    return df


def replace_missing_tokens(df, dataset):
    before = int(df.isnull().sum().sum())
    df = df.replace(MISSING_TOKENS, np.nan)
    after = int(df.isnull().sum().sum())
    if after > before:
        log_transformation(dataset, "missing tokens",
                           f"converted {after - before} placeholder values to NaN")
    return df


def coerce_numeric(df, columns, dataset):
    for col in columns:
        if col not in df.columns:
            continue
        before_dtype = str(df[col].dtype)
        before_null = int(df[col].isnull().sum())
        df[col] = pd.to_numeric(df[col], errors="coerce")
        after_null = int(df[col].isnull().sum())
        log_transformation(dataset, "type conversion",
                           f"{col}: {before_dtype} -> {df[col].dtype}")
        if after_null > before_null:
            log_issue(dataset, "high", f"non-numeric values in {col}",
                      after_null - before_null, "coerced to NaN")
    return df


def canonicalise(series, allowed):
    lookup = {value.lower(): value for value in allowed}
    return series.apply(lambda v: lookup.get(v.lower(), v) if isinstance(v, str) else v)


def canonicalise_country(series):
    return series.apply(
        lambda v: COUNTRY_CANONICAL.get(v.lower(), v) if isinstance(v, str) else v)


def report_missing(df, dataset):
    missing = df.isnull().sum()
    for col, count in missing.items():
        if count:
            log_issue(dataset, "medium", f"missing values in {col}", count,
                      "retained as NaN and excluded from column statistics")
    return missing


def drop_exact_duplicates(df, dataset):
    count = int(df.duplicated().sum())
    if count:
        df = df.drop_duplicates().reset_index(drop=True)
        log_issue(dataset, "high", "exact duplicate rows", count, "dropped")
        log_transformation(dataset, "duplicates", f"dropped {count} duplicate rows")
    else:
        log_issue(dataset, "none", "exact duplicate rows", 0, "no action required")
    return df


def check_primary_key(df, column, dataset):
    duplicated = int(df[column].duplicated().sum())
    nulls = int(df[column].isnull().sum())
    if duplicated:
        log_issue(dataset, "critical", f"duplicate primary key {column}", duplicated,
                  "first occurrence kept")
        df = df.drop_duplicates(subset=[column], keep="first").reset_index(drop=True)
    if nulls:
        log_issue(dataset, "critical", f"null primary key {column}", nulls, "rows dropped")
        df = df[df[column].notnull()].reset_index(drop=True)
    if not duplicated and not nulls:
        log_issue(dataset, "none", f"primary key {column} uniqueness", 0, "no action required")
    return df


def check_domain(df, column, allowed, dataset, severity="medium"):
    if column not in df.columns:
        return
    invalid = df[df[column].notnull() & ~df[column].isin(allowed)]
    if len(invalid):
        log_issue(dataset, severity, f"unexpected values in {column}", len(invalid),
                  f"flagged, expected one of {allowed}")
    else:
        log_issue(dataset, "none", f"{column} label consistency", 0, "no action required")


def check_range(df, column, low, high, dataset, severity="high"):
    if column not in df.columns:
        return
    invalid = df[df[column].notnull() & ((df[column] < low) | (df[column] > high))]
    if len(invalid):
        log_issue(dataset, severity, f"{column} outside [{low}, {high}]", len(invalid), "flagged")
    else:
        log_issue(dataset, "none", f"{column} within [{low}, {high}]", 0, "no action required")


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1 = np.radians(lat1)
    p2 = np.radians(lat2)
    dp = np.radians(lat2 - lat1)
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def clean_utilities(utilities):
    dataset = "utilities"
    utilities = replace_missing_tokens(utilities, dataset)
    utilities = strip_text(utilities, dataset)
    utilities = coerce_numeric(utilities, ["Utility ID"], dataset)
    utilities["Type"] = canonicalise(utilities["Type"], UTILITY_TYPES)
    utilities["Country"] = canonicalise_country(utilities["Country"])
    utilities["Active"] = utilities["Active"].apply(
        lambda v: v.upper() if isinstance(v, str) else v)
    report_missing(utilities, dataset)
    utilities = drop_exact_duplicates(utilities, dataset)
    utilities = check_primary_key(utilities, "Utility ID", dataset)
    check_domain(utilities, "Type", UTILITY_TYPES, dataset)
    check_domain(utilities, "Active", UTILITY_ACTIVE, dataset)
    duplicate_codes = int(utilities["Code"].duplicated().sum())
    if duplicate_codes:
        log_issue(dataset, "medium", "duplicate utility Code", duplicate_codes, "flagged")
    utilities["Utility ID"] = utilities["Utility ID"].astype(int)
    return utilities


def clean_substations(substations):
    dataset = "substations"
    substations = replace_missing_tokens(substations, dataset)
    substations = strip_text(substations, dataset)
    substations = coerce_numeric(
        substations,
        ["Substation ID", "Latitude", "Longitude", "Voltage (kV)",
         "Capacity (MVA)", "Commissioning Year"],
        dataset)

    before_country = substations["Country"].copy()
    substations["Country"] = canonicalise_country(substations["Country"])
    fixed = int((before_country != substations["Country"]).sum())
    if fixed:
        log_issue(dataset, "medium", "truncated country labels", fixed,
                  "standardised to full country names")
        log_transformation(dataset, "standardisation",
                           f"normalised {fixed} Country values (e.g. Cote -> Cote d'Ivoire)")

    substations["Type"] = canonicalise(substations["Type"], SUBSTATION_TYPES)
    substations["Status"] = canonicalise(substations["Status"], SUBSTATION_STATUS)

    report_missing(substations, dataset)
    substations = drop_exact_duplicates(substations, dataset)
    substations = check_primary_key(substations, "Substation ID", dataset)

    check_range(substations, "Latitude", LAT_RANGE[0], LAT_RANGE[1], dataset, "critical")
    check_range(substations, "Longitude", LON_RANGE[0], LON_RANGE[1], dataset, "critical")
    check_range(substations, "Commissioning Year", YEAR_RANGE[0], YEAR_RANGE[1], dataset)
    check_domain(substations, "Voltage (kV)", VALID_VOLTAGES, dataset, "high")
    check_domain(substations, "Type", SUBSTATION_TYPES, dataset)
    check_domain(substations, "Status", SUBSTATION_STATUS, dataset)

    non_positive = int((substations["Capacity (MVA)"] <= 0).sum())
    if non_positive:
        log_issue(dataset, "high", "non-positive Capacity (MVA)", non_positive, "flagged")
    else:
        log_issue(dataset, "none", "Capacity (MVA) positive", 0, "no action required")

    duplicate_names = int(substations["Name"].duplicated().sum())
    if duplicate_names:
        log_issue(dataset, "medium", "duplicate substation Name", duplicate_names,
                  "flagged, IDs remain unique")

    duplicate_coords = int(substations.duplicated(subset=["Latitude", "Longitude"]).sum())
    if duplicate_coords:
        log_issue(dataset, "medium", "substations sharing identical coordinates",
                  duplicate_coords, "flagged")

    substations["Substation ID"] = substations["Substation ID"].astype(int)
    substations["Voltage (kV)"] = substations["Voltage (kV)"].astype(int)
    substations["Commissioning Year"] = substations["Commissioning Year"].astype(int)
    return substations


def clean_lines(lines, utilities, substations):
    dataset = "lines"
    lines = replace_missing_tokens(lines, dataset)
    lines = strip_text(lines, dataset)
    lines = coerce_numeric(
        lines,
        ["Line ID", "Utility ID", "Source Substation ID", "Destination Substation ID",
         "Voltage (kV)", "Length (km)", "Capacity (MVA)"],
        dataset)

    lines["Status"] = canonicalise(lines["Status"], LINE_STATUS)
    lines["Line Type"] = canonicalise(lines["Line Type"], LINE_TYPES)

    report_missing(lines, dataset)
    lines = drop_exact_duplicates(lines, dataset)
    lines = check_primary_key(lines, "Line ID", dataset)

    check_domain(lines, "Voltage (kV)", VALID_VOLTAGES, dataset, "high")
    check_domain(lines, "Status", LINE_STATUS, dataset)
    check_domain(lines, "Line Type", LINE_TYPES, dataset)

    valid_substations = set(substations["Substation ID"])
    valid_utilities = set(utilities["Utility ID"])

    orphan_source = ~lines["Source Substation ID"].isin(valid_substations)
    orphan_dest = ~lines["Destination Substation ID"].isin(valid_substations)
    orphan_utility = ~lines["Utility ID"].isin(valid_utilities)
    orphan = orphan_source | orphan_dest | orphan_utility

    if int(orphan_source.sum()):
        log_issue(dataset, "critical", "Source Substation ID not present in substations.csv",
                  int(orphan_source.sum()), "row removed to preserve referential integrity")
    else:
        log_issue(dataset, "none", "Source Substation ID referential integrity", 0,
                  "no action required")

    if int(orphan_dest.sum()):
        log_issue(dataset, "critical", "Destination Substation ID not present in substations.csv",
                  int(orphan_dest.sum()), "row removed to preserve referential integrity")
    else:
        log_issue(dataset, "none", "Destination Substation ID referential integrity", 0,
                  "no action required")

    if int(orphan_utility.sum()):
        log_issue(dataset, "critical", "Utility ID not present in utilities.csv",
                  int(orphan_utility.sum()), "row removed to preserve referential integrity")
    else:
        log_issue(dataset, "none", "Utility ID referential integrity", 0, "no action required")

    rejected = lines[orphan].copy()
    if len(rejected):
        rejected.to_csv(REPORTS / "rejected_lines.csv", index=False)
        log_transformation(dataset, "referential integrity",
                           f"removed {len(rejected)} orphaned lines to reports/rejected_lines.csv")
    lines = lines[~orphan].reset_index(drop=True)

    self_loops = lines["Source Substation ID"] == lines["Destination Substation ID"]
    if int(self_loops.sum()):
        log_issue(dataset, "high", "line connects a substation to itself",
                  int(self_loops.sum()), "dropped")
        lines = lines[~self_loops].reset_index(drop=True)
    else:
        log_issue(dataset, "none", "self-referencing lines", 0, "no action required")

    for column in ["Line ID", "Utility ID", "Source Substation ID",
                   "Destination Substation ID"]:
        lines[column] = lines[column].astype(int)

    pair_key = pd.Series([tuple(sorted(pair)) for pair in zip(
        lines["Source Substation ID"], lines["Destination Substation ID"])])
    duplicate_pairs = int(pair_key.duplicated().sum())
    if duplicate_pairs:
        log_issue(dataset, "medium", "parallel lines between the same substation pair",
                  duplicate_pairs, "retained, valid in a meshed grid but flagged for review")
    else:
        log_issue(dataset, "none", "duplicate undirected substation pairs", 0,
                  "no action required")

    non_positive_length = int((lines["Length (km)"] <= 0).sum())
    if non_positive_length:
        log_issue(dataset, "high", "non-positive Length (km)", non_positive_length, "flagged")
    else:
        log_issue(dataset, "none", "Length (km) positive", 0, "no action required")

    coords = substations.set_index("Substation ID")[["Latitude", "Longitude",
                                                     "Voltage (kV)", "Name"]]
    src = coords.reindex(lines["Source Substation ID"].values)
    dst = coords.reindex(lines["Destination Substation ID"].values)

    geodesic = haversine_km(src["Latitude"].values, src["Longitude"].values,
                            dst["Latitude"].values, dst["Longitude"].values)
    lines["Geodesic Distance (km)"] = np.round(geodesic, 2)
    ratio = np.full(len(lines), np.nan)
    np.divide(lines["Length (km)"].values, geodesic, out=ratio, where=geodesic > 0)
    lines["Length Ratio"] = np.round(ratio, 3)
    implausible = int(np.nansum((ratio < 1.0) | (ratio > 2.0)))
    if implausible:
        log_issue(dataset, "medium", "Length (km) implausible against geodesic distance",
                  implausible, "flagged, routing slack outside 1.0-2.0x")
    else:
        log_issue(dataset, "none", "Length (km) consistent with coordinates", 0,
                  "no action required")

    endpoint_min_voltage = np.minimum(src["Voltage (kV)"].values, dst["Voltage (kV)"].values)
    voltage_mismatch = int((lines["Voltage (kV)"].values > endpoint_min_voltage).sum())
    if voltage_mismatch:
        log_issue(dataset, "high",
                  "line voltage exceeds the lower-rated endpoint substation voltage",
                  voltage_mismatch,
                  "flagged for engineering review, retained pending confirmation")
    else:
        log_issue(dataset, "none", "line voltage consistent with endpoints", 0,
                  "no action required")

    name_mismatch = int((lines["Source Substation"].values != src["Name"].values).sum() +
                        (lines["Destination Substation"].values != dst["Name"].values).sum())
    if name_mismatch:
        log_issue(dataset, "high", "denormalised substation name disagrees with substations.csv",
                  name_mismatch, "name refreshed from substations.csv")
        lines["Source Substation"] = src["Name"].values
        lines["Destination Substation"] = dst["Name"].values
        log_transformation(dataset, "standardisation",
                           f"refreshed {name_mismatch} denormalised substation names")
    else:
        log_issue(dataset, "none", "denormalised substation names match", 0,
                  "no action required")

    lines["Voltage (kV)"] = lines["Voltage (kV)"].astype(int)
    return lines


def write_summary_statistics(frames):
    for name, df in frames.items():
        numeric = df.select_dtypes(include=[np.number])
        if len(numeric.columns):
            numeric.describe().transpose().to_csv(REPORTS / f"summary_numeric_{name}.csv")
        categorical = df.select_dtypes(include=["object"])
        rows = []
        for col in categorical.columns:
            counts = categorical[col].value_counts(dropna=False)
            for value, count in counts.items():
                rows.append({"column": col, "value": value, "count": int(count)})
        if rows:
            pd.DataFrame(rows).to_csv(REPORTS / f"summary_categorical_{name}.csv", index=False)


def write_reports(raw_shapes, clean_shapes):
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "raw_row_counts": raw_shapes,
        "clean_row_counts": clean_shapes,
        "transformations": transformations,
        "issues": issues,
    }
    (REPORTS / "data_quality_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "none": 4}
    ranked = sorted(issues, key=lambda item: (severity_order.get(item["severity"], 5),
                                              item["dataset"]))
    detected = [item for item in ranked if item["severity"] != "none"]
    passed = [item for item in ranked if item["severity"] == "none"]

    md = ["# Task 1.1 Data Cleaning and Quality Report", ""]
    md.append(f"Generated: {report['generated_at']}")
    md.append("")
    md.append("## Row counts")
    md.append("")
    md.append("| Dataset | Raw rows | Clean rows | Difference |")
    md.append("| --- | --- | --- | --- |")
    for name in raw_shapes:
        diff = clean_shapes[name] - raw_shapes[name]
        md.append(f"| {name} | {raw_shapes[name]} | {clean_shapes[name]} | {diff} |")
    md.append("")
    md.append("## Transformations applied")
    md.append("")
    md.append("| Dataset | Step | Detail |")
    md.append("| --- | --- | --- |")
    for item in transformations:
        md.append(f"| {item['dataset']} | {item['step']} | {item['detail']} |")
    md.append("")
    md.append("## Issues detected")
    md.append("")
    if detected:
        md.append("| Severity | Dataset | Issue | Count | Action |")
        md.append("| --- | --- | --- | --- | --- |")
        for item in detected:
            md.append(f"| {item['severity']} | {item['dataset']} | {item['issue']} | "
                      f"{item['count']} | {item['action']} |")
    else:
        md.append("No issues detected.")
    md.append("")
    md.append("## Checks passed with no issues")
    md.append("")
    md.append("| Dataset | Check |")
    md.append("| --- | --- |")
    for item in passed:
        md.append(f"| {item['dataset']} | {item['issue']} |")
    md.append("")
    (REPORTS / "data_quality_report.md").write_text("\n".join(md), encoding="utf-8")


def main():
    CLEAN.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    utilities_raw, substations_raw, lines_raw = load_raw()
    raw_shapes = {
        "utilities": len(utilities_raw),
        "substations": len(substations_raw),
        "lines": len(lines_raw),
    }

    print("Raw shapes:", raw_shapes)
    for name, df in [("utilities", utilities_raw), ("substations", substations_raw),
                     ("lines", lines_raw)]:
        print(f"\n{name} dtypes and non-null counts")
        df.info()
        print(f"\n{name} missing values")
        print(df.isnull().sum())

    utilities = clean_utilities(utilities_raw.copy())
    substations = clean_substations(substations_raw.copy())
    lines = clean_lines(lines_raw.copy(), utilities, substations)

    clean_shapes = {
        "utilities": len(utilities),
        "substations": len(substations),
        "lines": len(lines),
    }

    utilities.to_csv(CLEAN / "utilities_clean.csv", index=False)
    substations.to_csv(CLEAN / "substations_clean.csv", index=False)
    lines.to_csv(CLEAN / "lines_clean.csv", index=False)

    write_summary_statistics({"utilities": utilities, "substations": substations, "lines": lines})
    write_reports(raw_shapes, clean_shapes)

    print("\nClean shapes:", clean_shapes)
    print(f"Transformations logged: {len(transformations)}")
    print(f"Checks recorded: {len(issues)} "
          f"({len([i for i in issues if i['severity'] != 'none'])} with findings)")
    print(f"Clean data: {CLEAN}")
    print(f"Reports: {REPORTS}")
    return utilities, substations, lines


if __name__ == "__main__":
    main()
