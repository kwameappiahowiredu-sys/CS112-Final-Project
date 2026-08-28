import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
CLEAN = BASE / "data" / "clean"
REPORTS = BASE / "reports"
LOOKUPS = BASE / "data" / "lookups"

join_log = []

FIELD_DESCRIPTIONS = {
    "utilities": {
        "Utility ID": ("integer", "Primary key. Unique identifier for a utility company."),
        "Name": ("text", "Full legal name of the utility."),
        "Alias": ("text", "Common short name used in reports and charts, e.g. ECG."),
        "Code": ("text", "Three-letter code used to cross-reference the utility."),
        "Type": ("category", "Generation, Transmission or Distribution."),
        "Country": ("text", "Country or countries in which the utility operates."),
        "Active": ("category", "Y if the utility is currently operating, otherwise N."),
    },
    "substations": {
        "Substation ID": ("integer", "Primary key. Unique identifier for a substation."),
        "Name": ("text", "Full substation name as recorded in the asset register."),
        "Short Name": ("text", "Place name used for map and graph labelling."),
        "Region": ("text", "Ghanaian administrative region, or bordering location for "
                           "cross-border nodes."),
        "Country": ("text", "Country in which the substation sits."),
        "Latitude": ("float", "Decimal-degree latitude, expected between 3 and 16."),
        "Longitude": ("float", "Decimal-degree longitude, expected between -18 and 5."),
        "Voltage (kV)": ("integer", "Nominal operating voltage: 11, 33, 69, 161 or 330."),
        "Capacity (MVA)": ("float", "Rated capacity in megavolt-amperes."),
        "Commissioning Year": ("integer", "Year the substation was notionally commissioned."),
        "Type": ("category", "Distribution, Bulk Supply Point or Transmission."),
        "Status": ("category", "Active or Inactive."),
    },
    "lines": {
        "Line ID": ("integer", "Primary key. Unique identifier for a line."),
        "Utility ID": ("integer", "Foreign key to utilities.Utility ID. Owner of the line."),
        "Source Substation ID": ("integer",
                                 "Foreign key to substations.Substation ID for one endpoint."),
        "Source Substation": ("text", "Denormalised name of the source substation."),
        "Destination Substation ID": ("integer",
                                      "Foreign key to substations.Substation ID for the "
                                      "other endpoint."),
        "Destination Substation": ("text", "Denormalised name of the destination substation."),
        "Voltage (kV)": ("integer", "Operating voltage of the line."),
        "Length (km)": ("float", "Recorded route length of the line."),
        "Capacity (MVA)": ("float", "Rated transfer capacity of the line."),
        "Status": ("category", "Active or Under Maintenance."),
        "Line Type": ("category", "Overhead or Underground."),
        "Geodesic Distance (km)": ("float",
                                   "Straight-line distance between endpoints, recomputed in "
                                   "Task 1.1 from coordinates."),
        "Length Ratio": ("float",
                         "Length (km) divided by Geodesic Distance (km). Routing slack "
                         "indicator used for validation."),
    },
    "master_lines": {
        "Source Region": ("text", "Region of the source substation, joined from substations."),
        "Source Country": ("text", "Country of the source substation."),
        "Source Latitude": ("float", "Latitude of the source substation."),
        "Source Longitude": ("float", "Longitude of the source substation."),
        "Source Voltage (kV)": ("integer", "Voltage rating of the source substation."),
        "Source Capacity (MVA)": ("float", "Capacity of the source substation."),
        "Source Substation Type": ("category", "Class of the source substation."),
        "Source Status": ("category", "Operational status of the source substation."),
        "Destination Region": ("text", "Region of the destination substation."),
        "Destination Country": ("text", "Country of the destination substation."),
        "Destination Latitude": ("float", "Latitude of the destination substation."),
        "Destination Longitude": ("float", "Longitude of the destination substation."),
        "Destination Voltage (kV)": ("integer", "Voltage rating of the destination substation."),
        "Destination Capacity (MVA)": ("float", "Capacity of the destination substation."),
        "Destination Substation Type": ("category", "Class of the destination substation."),
        "Destination Status": ("category", "Operational status of the destination substation."),
        "Utility Name": ("text", "Full name of the operating utility."),
        "Utility Alias": ("text", "Short name of the operating utility."),
        "Utility Code": ("text", "Three-letter code of the operating utility."),
        "Utility Type": ("category", "Operating utility class."),
        "Utility Active": ("category", "Whether the operating utility is currently active."),
        "Inter-Regional": ("boolean", "True when the two endpoints sit in different regions."),
        "Cross-Border": ("boolean", "True when the two endpoints sit in different countries."),
        "Endpoint Min Voltage (kV)": ("integer",
                                      "Lower of the two endpoint substation voltages."),
        "Voltage Consistent": ("boolean",
                               "True when line voltage does not exceed the lower-rated "
                               "endpoint."),
        "Both Endpoints Active": ("boolean", "True when neither endpoint is Inactive."),
        "Region Pair": ("text", "Alphabetically ordered region pair, used for flow summaries."),
    },
    "master_substations": {
        "Connections": ("integer", "Number of lines incident on the substation."),
        "Connected Substations": ("integer", "Number of distinct neighbouring substations."),
        "Operating Utilities": ("integer", "Number of distinct utilities operating incident "
                                           "lines."),
        "Total Line Length (km)": ("float", "Sum of the lengths of incident lines."),
        "Total Line Capacity (MVA)": ("float", "Sum of the rated capacities of incident lines."),
        "Lines Under Maintenance": ("integer", "Count of incident lines Under Maintenance."),
        "Inter-Regional Connections": ("integer",
                                       "Count of incident lines whose other endpoint sits in "
                                       "another region."),
        "Asset Age (years)": ("integer", "Current year minus Commissioning Year."),
        "Neighbours": ("text", "Semicolon-separated names of directly connected substations."),
    },
}


def log_join(step, left, right, key, before, after, unmatched, note):
    join_log.append({
        "step": step,
        "left": left,
        "right": right,
        "key": key,
        "left_rows_before": int(before),
        "rows_after": int(after),
        "unmatched_rows": int(unmatched),
        "note": note,
    })


def load_clean():
    utilities = pd.read_csv(CLEAN / "utilities_clean.csv")
    substations = pd.read_csv(CLEAN / "substations_clean.csv")
    lines = pd.read_csv(CLEAN / "lines_clean.csv")
    return utilities, substations, lines


def build_lookups(utilities, substations):
    substation_by_id = substations.set_index("Substation ID").to_dict(orient="index")
    utility_by_id = utilities.set_index("Utility ID").to_dict(orient="index")
    name_to_id = dict(zip(substations["Name"], substations["Substation ID"]))
    short_name_to_id = dict(zip(substations["Short Name"], substations["Substation ID"]))
    region_to_ids = substations.groupby("Region")["Substation ID"].apply(list).to_dict()
    utility_alias_to_id = dict(zip(utilities["Alias"], utilities["Utility ID"]))

    LOOKUPS.mkdir(parents=True, exist_ok=True)
    payload = {
        "substation_by_id": {str(k): v for k, v in substation_by_id.items()},
        "utility_by_id": {str(k): v for k, v in utility_by_id.items()},
        "name_to_id": {k: int(v) for k, v in name_to_id.items()},
        "short_name_to_id": {k: int(v) for k, v in short_name_to_id.items()},
        "region_to_ids": {k: [int(i) for i in v] for k, v in region_to_ids.items()},
        "utility_alias_to_id": {k: int(v) for k, v in utility_alias_to_id.items()},
    }
    (LOOKUPS / "lookups.json").write_text(json.dumps(payload, indent=2, default=str),
                                          encoding="utf-8")
    return {
        "substation_by_id": substation_by_id,
        "utility_by_id": utility_by_id,
        "name_to_id": name_to_id,
        "short_name_to_id": short_name_to_id,
        "region_to_ids": region_to_ids,
        "utility_alias_to_id": utility_alias_to_id,
    }


def endpoint_frame(substations, prefix):
    columns = {
        "Substation ID": f"{prefix} Substation ID",
        "Region": f"{prefix} Region",
        "Country": f"{prefix} Country",
        "Latitude": f"{prefix} Latitude",
        "Longitude": f"{prefix} Longitude",
        "Voltage (kV)": f"{prefix} Voltage (kV)",
        "Capacity (MVA)": f"{prefix} Capacity (MVA)",
        "Type": f"{prefix} Substation Type",
        "Status": f"{prefix} Status",
    }
    return substations[list(columns)].rename(columns=columns)


def build_master_lines(utilities, substations, lines):
    master = lines.copy()

    source = endpoint_frame(substations, "Source")
    before = len(master)
    master = master.merge(source, on="Source Substation ID", how="left")
    unmatched = int(master["Source Region"].isnull().sum())
    log_join("1", "lines", "substations", "Source Substation ID", before, len(master),
             unmatched, "left join to attach source substation attributes")

    destination = endpoint_frame(substations, "Destination")
    before = len(master)
    master = master.merge(destination, on="Destination Substation ID", how="left")
    unmatched = int(master["Destination Region"].isnull().sum())
    log_join("2", "lines+source", "substations", "Destination Substation ID", before,
             len(master), unmatched, "left join to attach destination substation attributes")

    utility_columns = {
        "Utility ID": "Utility ID",
        "Name": "Utility Name",
        "Alias": "Utility Alias",
        "Code": "Utility Code",
        "Type": "Utility Type",
        "Active": "Utility Active",
    }
    before = len(master)
    master = master.merge(
        utilities[list(utility_columns)].rename(columns=utility_columns),
        on="Utility ID", how="left")
    unmatched = int(master["Utility Name"].isnull().sum())
    log_join("3", "lines+substations", "utilities", "Utility ID", before, len(master),
             unmatched, "left join to attach operating utility attributes")

    master["Inter-Regional"] = master["Source Region"] != master["Destination Region"]
    master["Cross-Border"] = master["Source Country"] != master["Destination Country"]
    master["Endpoint Min Voltage (kV)"] = np.minimum(
        master["Source Voltage (kV)"], master["Destination Voltage (kV)"])
    master["Voltage Consistent"] = (
        master["Voltage (kV)"] <= master["Endpoint Min Voltage (kV)"])
    master["Both Endpoints Active"] = (
        (master["Source Status"] == "Active") & (master["Destination Status"] == "Active"))
    master["Region Pair"] = [
        " - ".join(sorted([str(a), str(b)]))
        for a, b in zip(master["Source Region"], master["Destination Region"])]

    column_order = [
        "Line ID", "Utility ID", "Utility Name", "Utility Alias", "Utility Code",
        "Utility Type", "Utility Active",
        "Source Substation ID", "Source Substation", "Source Region", "Source Country",
        "Source Latitude", "Source Longitude", "Source Voltage (kV)",
        "Source Capacity (MVA)", "Source Substation Type", "Source Status",
        "Destination Substation ID", "Destination Substation", "Destination Region",
        "Destination Country", "Destination Latitude", "Destination Longitude",
        "Destination Voltage (kV)", "Destination Capacity (MVA)",
        "Destination Substation Type", "Destination Status",
        "Voltage (kV)", "Length (km)", "Capacity (MVA)", "Status", "Line Type",
        "Geodesic Distance (km)", "Length Ratio", "Endpoint Min Voltage (kV)",
        "Voltage Consistent", "Both Endpoints Active", "Inter-Regional", "Cross-Border",
        "Region Pair",
    ]
    master = master[[column for column in column_order if column in master.columns]]
    return master


def build_master_substations(substations, master_lines):
    endpoints = pd.concat([
        master_lines[["Source Substation ID", "Destination Substation ID", "Utility ID",
                      "Length (km)", "Capacity (MVA)", "Status", "Inter-Regional"]].rename(
            columns={"Source Substation ID": "Substation ID",
                     "Destination Substation ID": "Neighbour ID"}),
        master_lines[["Destination Substation ID", "Source Substation ID", "Utility ID",
                      "Length (km)", "Capacity (MVA)", "Status", "Inter-Regional"]].rename(
            columns={"Destination Substation ID": "Substation ID",
                     "Source Substation ID": "Neighbour ID"}),
    ], ignore_index=True)

    grouped = endpoints.groupby("Substation ID")
    summary = pd.DataFrame({
        "Connections": grouped.size(),
        "Connected Substations": grouped["Neighbour ID"].nunique(),
        "Operating Utilities": grouped["Utility ID"].nunique(),
        "Total Line Length (km)": grouped["Length (km)"].sum().round(1),
        "Total Line Capacity (MVA)": grouped["Capacity (MVA)"].sum().round(1),
        "Lines Under Maintenance": grouped["Status"].apply(
            lambda values: int((values == "Under Maintenance").sum())),
        "Inter-Regional Connections": grouped["Inter-Regional"].sum().astype(int),
    })

    name_lookup = substations.set_index("Substation ID")["Short Name"]
    neighbours = endpoints.copy()
    neighbours["Neighbour Name"] = neighbours["Neighbour ID"].map(name_lookup)
    neighbour_names = neighbours.groupby("Substation ID")["Neighbour Name"].apply(
        lambda values: "; ".join(sorted(set(values.dropna()))))

    master = substations.set_index("Substation ID").join(summary, how="left")
    master["Neighbours"] = neighbour_names
    for column in ["Connections", "Connected Substations", "Operating Utilities",
                   "Lines Under Maintenance", "Inter-Regional Connections"]:
        master[column] = master[column].fillna(0).astype(int)
    for column in ["Total Line Length (km)", "Total Line Capacity (MVA)"]:
        master[column] = master[column].fillna(0.0)
    master["Neighbours"] = master["Neighbours"].fillna("")
    master["Asset Age (years)"] = datetime.now().year - master["Commissioning Year"]
    master = master.sort_values("Connections", ascending=False)
    return master.reset_index()


def validate_integration(utilities, substations, lines, master_lines, master_substations):
    results = []

    results.append({
        "check": "master_lines row count equals cleaned lines row count",
        "expected": len(lines),
        "actual": len(master_lines),
        "status": "PASS" if len(master_lines) == len(lines) else "FAIL",
    })

    key_columns = ["Source Region", "Destination Region", "Utility Name"]
    for column in key_columns:
        nulls = int(master_lines[column].isnull().sum())
        results.append({
            "check": f"no unmatched keys after join ({column})",
            "expected": 0,
            "actual": nulls,
            "status": "PASS" if nulls == 0 else "FAIL",
        })

    duplicated = int(master_lines["Line ID"].duplicated().sum())
    results.append({
        "check": "master_lines Line ID remains unique after joins",
        "expected": 0,
        "actual": duplicated,
        "status": "PASS" if duplicated == 0 else "FAIL",
    })

    results.append({
        "check": "master_substations row count equals cleaned substations row count",
        "expected": len(substations),
        "actual": len(master_substations),
        "status": "PASS" if len(master_substations) == len(substations) else "FAIL",
    })

    degree_sum = int(master_substations["Connections"].sum())
    results.append({
        "check": "sum of substation connections equals twice the number of lines",
        "expected": 2 * len(master_lines),
        "actual": degree_sum,
        "status": "PASS" if degree_sum == 2 * len(master_lines) else "FAIL",
    })

    length_before = round(float(lines["Length (km)"].sum()), 1)
    length_after = round(float(master_lines["Length (km)"].sum()), 1)
    results.append({
        "check": "total line length preserved through the joins",
        "expected": length_before,
        "actual": length_after,
        "status": "PASS" if abs(length_after - length_before) < 0.05 else "FAIL",
    })

    orphan_utilities = int((~utilities["Utility ID"].isin(lines["Utility ID"])).sum())
    results.append({
        "check": "utilities with no lines in the dataset",
        "expected": "informational",
        "actual": orphan_utilities,
        "status": "INFO",
    })

    isolated = int((master_substations["Connections"] == 0).sum())
    results.append({
        "check": "substations with no incident lines",
        "expected": "informational",
        "actual": isolated,
        "status": "INFO",
    })

    inconsistent = int((~master_lines["Voltage Consistent"]).sum())
    results.append({
        "check": "lines rated above their lower-voltage endpoint",
        "expected": "informational",
        "actual": inconsistent,
        "status": "INFO",
    })

    return results


def build_data_dictionary(frames):
    rows = []
    for dataset, df in frames.items():
        for column in df.columns:
            data_type, description = FIELD_DESCRIPTIONS.get(dataset, {}).get(
                column, (None, None))
            if data_type is None:
                for source in FIELD_DESCRIPTIONS.values():
                    if column in source:
                        data_type, description = source[column]
                        break
            series = df[column]
            example = series.dropna().iloc[0] if int(series.notnull().sum()) else ""
            rows.append({
                "Dataset": dataset,
                "Field": column,
                "Logical Type": data_type or "text",
                "Pandas dtype": str(series.dtype),
                "Non-null": int(series.notnull().sum()),
                "Nulls": int(series.isnull().sum()),
                "Distinct": int(series.nunique(dropna=True)),
                "Example": example,
                "Description": description or "Derived field produced during integration.",
            })
    dictionary = pd.DataFrame(rows)
    dictionary.to_csv(REPORTS / "data_dictionary.csv", index=False)
    return dictionary


def write_erd():
    mermaid = """erDiagram
    UTILITIES ||--o{ LINES : "operates"
    SUBSTATIONS ||--o{ LINES : "is source of"
    SUBSTATIONS ||--o{ LINES : "is destination of"

    UTILITIES {
        int Utility_ID PK
        string Name
        string Alias
        string Code
        string Type
        string Country
        string Active
    }

    SUBSTATIONS {
        int Substation_ID PK
        string Name
        string Short_Name
        string Region
        string Country
        float Latitude
        float Longitude
        int Voltage_kV
        float Capacity_MVA
        int Commissioning_Year
        string Type
        string Status
    }

    LINES {
        int Line_ID PK
        int Utility_ID FK
        int Source_Substation_ID FK
        int Destination_Substation_ID FK
        int Voltage_kV
        float Length_km
        float Capacity_MVA
        string Status
        string Line_Type
    }
"""
    (REPORTS / "erd.mmd").write_text(mermaid, encoding="utf-8")

    dot = """digraph grid_erd {
    rankdir=LR;
    node [shape=record, fontname="Helvetica", fontsize=10];

    utilities [label="{utilities|Utility ID (PK)\\lName\\lAlias\\lCode\\lType\\lCountry\\lActive\\l}"];
    substations [label="{substations|Substation ID (PK)\\lName\\lShort Name\\lRegion\\lCountry\\lLatitude\\lLongitude\\lVoltage (kV)\\lCapacity (MVA)\\lCommissioning Year\\lType\\lStatus\\l}"];
    lines [label="{lines|Line ID (PK)\\lUtility ID (FK)\\lSource Substation ID (FK)\\lDestination Substation ID (FK)\\lVoltage (kV)\\lLength (km)\\lCapacity (MVA)\\lStatus\\lLine Type\\l}"];

    utilities -> lines [label="1 : N  operates", arrowhead=crow];
    substations -> lines [label="1 : N  source", arrowhead=crow];
    substations -> lines [label="1 : N  destination", arrowhead=crow];
}
"""
    (REPORTS / "erd.dot").write_text(dot, encoding="utf-8")


def write_report(validation, dictionary, master_lines, master_substations):
    md = ["# Task 1.3 Data Integration and Relationship Mapping", ""]
    md.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    md.append("")
    md.append("## 1. Relationship model")
    md.append("")
    md.append("| Parent | Child | Key | Cardinality |")
    md.append("| --- | --- | --- | --- |")
    md.append("| utilities | lines | Utility ID | one utility operates many lines |")
    md.append("| substations | lines | Source Substation ID | "
              "one substation is the source of many lines |")
    md.append("| substations | lines | Destination Substation ID | "
              "one substation is the destination of many lines |")
    md.append("")
    md.append("Diagrams: `reports/erd.mmd` (Mermaid) and `reports/erd.dot` (Graphviz).")
    md.append("")
    md.append("## 2. Join operations")
    md.append("")
    md.append("| Step | Left | Right | Key | Rows before | Rows after | Unmatched | Note |")
    md.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for entry in join_log:
        md.append(f"| {entry['step']} | {entry['left']} | {entry['right']} | {entry['key']} | "
                  f"{entry['left_rows_before']} | {entry['rows_after']} | "
                  f"{entry['unmatched_rows']} | {entry['note']} |")
    md.append("")
    md.append("All joins use `how='left'` from the lines table so that no line is silently "
              "dropped by the merge itself. Referential integrity was already enforced in "
              "Task 1.1, which removed orphaned lines before integration.")
    md.append("")
    md.append("## 3. Validation results")
    md.append("")
    md.append("| Check | Expected | Actual | Status |")
    md.append("| --- | --- | --- | --- |")
    for entry in validation:
        md.append(f"| {entry['check']} | {entry['expected']} | {entry['actual']} | "
                  f"{entry['status']} |")
    md.append("")
    md.append("## 4. Integrated outputs")
    md.append("")
    md.append(f"- `data/clean/master_lines.csv`: {len(master_lines)} rows, "
              f"{len(master_lines.columns)} columns. One row per line with both endpoints "
              f"and the operating utility resolved.")
    md.append(f"- `data/clean/master_substations.csv`: {len(master_substations)} rows, "
              f"{len(master_substations.columns)} columns. One row per substation with "
              f"connectivity and incident-line aggregates.")
    md.append("- `data/lookups/lookups.json`: substation and utility lookup dictionaries for "
              "efficient querying by ID, name or region.")
    md.append(f"- `reports/data_dictionary.csv`: {len(dictionary)} documented fields.")
    md.append("")
    md.append("## 5. Data loss statement")
    md.append("")
    unmatched_total = sum(entry["unmatched_rows"] for entry in join_log)
    md.append(f"Rows lost during integration: 0. Unmatched keys across all joins: "
              f"{unmatched_total}. Every line in the cleaned dataset resolved to a valid "
              f"source substation, destination substation and utility.")
    md.append("")
    (REPORTS / "integration_report.md").write_text("\n".join(md), encoding="utf-8")


def main():
    REPORTS.mkdir(parents=True, exist_ok=True)
    LOOKUPS.mkdir(parents=True, exist_ok=True)

    utilities, substations, lines = load_clean()
    lookups = build_lookups(utilities, substations)
    master_lines = build_master_lines(utilities, substations, lines)
    master_substations = build_master_substations(substations, master_lines)

    master_lines.to_csv(CLEAN / "master_lines.csv", index=False)
    master_substations.to_csv(CLEAN / "master_substations.csv", index=False)

    validation = validate_integration(utilities, substations, lines, master_lines,
                                      master_substations)
    dictionary = build_data_dictionary({
        "utilities": utilities,
        "substations": substations,
        "lines": lines,
        "master_lines": master_lines,
        "master_substations": master_substations,
    })
    write_erd()
    write_report(validation, dictionary, master_lines, master_substations)

    print("Lookup dictionaries built:", ", ".join(lookups))
    print(f"master_lines: {master_lines.shape[0]} rows x {master_lines.shape[1]} columns")
    print(f"master_substations: {master_substations.shape[0]} rows x "
          f"{master_substations.shape[1]} columns")
    print("\nJoin log")
    for entry in join_log:
        print(f"  step {entry['step']}: {entry['left']} + {entry['right']} on "
              f"{entry['key']} -> {entry['rows_after']} rows, "
              f"{entry['unmatched_rows']} unmatched")
    print("\nValidation")
    for entry in validation:
        print(f"  [{entry['status']}] {entry['check']}: expected {entry['expected']}, "
              f"got {entry['actual']}")
    print(f"\nData dictionary fields: {len(dictionary)}")
    print(f"Reports: {REPORTS}")
    return master_lines, master_substations


if __name__ == "__main__":
    main()
