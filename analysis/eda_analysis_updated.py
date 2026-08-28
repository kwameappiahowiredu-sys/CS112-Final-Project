from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent
CLEAN = BASE / "data" / "clean"
REPORTS = BASE / "reports"
TABLES = REPORTS / "eda_tables"
FIGURES = BASE / "figures"

plt.rcParams["figure.autolayout"] = True
plt.rcParams["axes.grid"] = True
plt.rcParams["grid.alpha"] = 0.3

def load_clean():
    utilities = pd.read_csv(CLEAN / "utilities_clean.csv")
    substations = pd.read_csv(CLEAN / "substations_clean.csv")
    lines = pd.read_csv(CLEAN / "lines_clean.csv")
    return utilities, substations, lines

def save_table(df, name):
    df.to_csv(TABLES / f"{name}.csv", index=True)

def to_md(df, index=True, index_label=""):
    frame = df.reset_index() if index else df
    if index and index_label:
        frame = frame.rename(columns={frame.columns[0]: index_label})
    headers = [str(col) for col in frame.columns]
    rows = ["| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |"]
    for values in frame.itertuples(index=False):
        rows.append("| " + " | ".join(
            f"{value:g}" if isinstance(value, float) else str(value)
            for value in values) + " |")
    return "\n".join(rows)

def bar_chart(series, title, xlabel, ylabel, filename, rotation=45, color="#1f77b4"):
    fig, ax = plt.subplots(figsize=(10, 6))
    series.plot(kind="bar", ax=ax, color=color, edgecolor="black", linewidth=0.4)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    plt.setp(ax.get_xticklabels(), rotation=rotation, ha="right" if rotation else "center")
    fig.savefig(FIGURES / filename, dpi=150)
    plt.close(fig)

def histogram(values, bins, title, xlabel, ylabel, filename, color="#2ca02c"):
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(values.dropna(), bins=bins, color=color, edgecolor="black", linewidth=0.4)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    fig.savefig(FIGURES / filename, dpi=150)
    plt.close(fig)

def stacked_chart(frame, title, xlabel, ylabel, filename, rotation=45):
    fig, ax = plt.subplots(figsize=(10, 6))
    frame.plot(kind="bar", stacked=True, ax=ax, edgecolor="black", linewidth=0.4)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.legend(title=frame.columns.name or "")
    plt.setp(ax.get_xticklabels(), rotation=rotation, ha="right" if rotation else "center")
    fig.savefig(FIGURES / filename, dpi=150)
    plt.close(fig)

def descriptive_statistics(utilities, substations, lines):
    tables = {}
    tables["substations_numeric"] = substations[
        ["Latitude", "Longitude", "Voltage (kV)", "Capacity (MVA)", "Commissioning Year"]
    ].describe().transpose()
    tables["lines_numeric"] = lines[
        ["Voltage (kV)", "Length (km)", "Capacity (MVA)", "Geodesic Distance (km)"]
    ].describe().transpose()
    tables["utilities_numeric"] = utilities[["Utility ID"]].describe().transpose()
    for name, table in tables.items():
        save_table(table.round(3), f"describe_{name}")
    return tables

def frequency_distributions(utilities, substations, lines):
    frequencies = {
        "substation_region": substations["Region"].value_counts(),
        "substation_country": substations["Country"].value_counts(),
        "substation_voltage": substations["Voltage (kV)"].value_counts().sort_index(),
        "substation_type": substations["Type"].value_counts(),
        "substation_status": substations["Status"].value_counts(),
        "line_voltage": lines["Voltage (kV)"].value_counts().sort_index(),
        "line_status": lines["Status"].value_counts(),
        "line_type": lines["Line Type"].value_counts(),
        "utility_type": utilities["Type"].value_counts(),
        "utility_country": utilities["Country"].value_counts(),
        "utility_active": utilities["Active"].value_counts(),
    }
    for name, series in frequencies.items():
        save_table(series.rename("count").to_frame(), f"frequency_{name}")
    return frequencies

def utility_footprint(utilities, lines):
    counts = lines["Utility ID"].value_counts().rename("Lines Operated")
    footprint = utilities.set_index("Utility ID")[["Name", "Alias", "Type", "Country"]].join(
        counts, how="left")
    footprint["Lines Operated"] = footprint["Lines Operated"].fillna(0).astype(int)
    footprint["Total Length (km)"] = lines.groupby("Utility ID")["Length (km)"].sum().round(1)
    footprint["Total Length (km)"] = footprint["Total Length (km)"].fillna(0)
    footprint["Mean Line Capacity (MVA)"] = (
        lines.groupby("Utility ID")["Capacity (MVA)"].mean().round(1))
    footprint = footprint.sort_values("Lines Operated", ascending=False)
    save_table(footprint, "utility_footprint")
    return footprint

def substation_connectivity(substations, lines):
    endpoints = pd.concat([lines["Source Substation ID"], lines["Destination Substation ID"]])
    degree = endpoints.value_counts().rename("Connections")
    connectivity = substations.set_index("Substation ID")[
        ["Name", "Short Name", "Region", "Country", "Voltage (kV)", "Capacity (MVA)",
         "Type", "Status"]].join(degree, how="left")
    connectivity["Connections"] = connectivity["Connections"].fillna(0).astype(int)
    connectivity = connectivity.sort_values("Connections", ascending=False)
    save_table(connectivity, "substation_connectivity")
    return connectivity

def regional_profile(substations, lines):
    region_lookup = substations.set_index("Substation ID")["Region"]
    lines = lines.copy()
    lines["Source Region"] = lines["Source Substation ID"].map(region_lookup)
    lines["Destination Region"] = lines["Destination Substation ID"].map(region_lookup)
    lines["Inter-Regional"] = lines["Source Region"] != lines["Destination Region"]

    profile = pd.DataFrame({
        "Substations": substations.groupby("Region").size(),
        "Total Capacity (MVA)": substations.groupby("Region")["Capacity (MVA)"].sum().round(1),
        "Mean Capacity (MVA)": substations.groupby("Region")["Capacity (MVA)"].mean().round(1),
        "Median Commissioning Year": substations.groupby("Region")["Commissioning Year"].median(),
        "Active Substations": substations[substations["Status"] == "Active"].groupby("Region").size(),
    })
    profile["Active Substations"] = profile["Active Substations"].fillna(0).astype(int)

    internal = lines[~lines["Inter-Regional"]].groupby("Source Region").size()
    outgoing = lines[lines["Inter-Regional"]].groupby("Source Region").size()
    incoming = lines[lines["Inter-Regional"]].groupby("Destination Region").size()
    profile["Internal Lines"] = internal.reindex(profile.index).fillna(0).astype(int)
    profile["Inter-Regional Lines"] = (
        outgoing.reindex(profile.index).fillna(0)
        + incoming.reindex(profile.index).fillna(0)).astype(int)
    profile = profile.sort_values("Substations", ascending=False)
    save_table(profile, "regional_profile")

    flows = lines[lines["Inter-Regional"]].groupby(
        ["Source Region", "Destination Region"]).size().rename("Lines").sort_values(
        ascending=False).to_frame()
    save_table(flows, "inter_regional_flows")
    return profile, lines

def build_figures(utilities, substations, lines, footprint, connectivity, profile,
                  lines_with_regions):
    bar_chart(substations["Region"].value_counts(),
              "Substations by Region", "Region", "Number of Substations",
              "01_substations_by_region.png")
    bar_chart(substations["Voltage (kV)"].value_counts().sort_index(),
              "Substation Voltage Level Distribution", "Voltage (kV)", "Number of Substations",
              "02_substation_voltage_levels.png", rotation=0, color="#ff7f0e")
    bar_chart(substations["Type"].value_counts(),
              "Substations by Type", "Substation Type", "Count",
              "03_substation_types.png", rotation=0, color="#9467bd")
    bar_chart(substations["Status"].value_counts(),
              "Substation Operational Status", "Status", "Count",
              "04_substation_status.png", rotation=0, color="#8c564b")
    histogram(substations["Capacity (MVA)"], 12,
              "Distribution of Substation Capacity", "Capacity (MVA)", "Number of Substations",
              "05_substation_capacity_distribution.png")
    histogram(substations["Commissioning Year"], 12,
              "Substation Commissioning Year Distribution", "Commissioning Year",
              "06_commissioning_year_distribution.png",
              color="#d62728")
    bar_chart(connectivity.head(10).set_index("Short Name")["Connections"],
              "Top 10 Most-Connected Substations", "Substation", "Number of Lines",
              "07_top_connected_substations.png", color="#17becf")
    bar_chart(footprint.set_index("Alias")["Lines Operated"],
              "Lines Operated by Utility", "Utility", "Number of Lines",
              "08_lines_by_utility.png", rotation=0, color="#1f77b4")
    histogram(lines["Length (km)"], 12,
              "Distribution of Line Length", "Length (km)", "Number of Lines",
              "09_line_length_distribution.png", color="#7f7f7f")
    status_by_utility = pd.crosstab(
        lines_with_regions["Utility ID"].map(utilities.set_index("Utility ID")["Alias"]),
        lines_with_regions["Status"])
    stacked_chart(status_by_utility, "Line Status by Utility", "Utility", "Number of Lines",
                  "10_line_status_by_utility.png", rotation=0)
    bar_chart(profile["Mean Capacity (MVA)"],
              "Mean Substation Capacity by Region", "Region", "Mean Capacity (MVA)",
              "11_mean_capacity_by_region.png", color="#e377c2")
    bar_chart(profile["Median Commissioning Year"],
              "Median Commissioning Year by Region", "Region", "Median Commissioning Year",
              "12_median_commissioning_year_by_region.png", color="#bcbd22")
    return status_by_utility

def build_findings(utilities, substations, lines, footprint, connectivity, profile):
    total_capacity = substations["Capacity (MVA)"].sum()
    top5_capacity = connectivity.sort_values("Capacity (MVA)", ascending=False).head(5)
    isolated = connectivity[connectivity["Connections"] == 0]
    maintenance = lines[lines["Status"] == "Under Maintenance"]
    inactive = substations[substations["Status"] == "Inactive"]
    cross_border = substations[substations["Country"] != "Ghana"]

    findings = {
        "substation_count": len(substations),
        "line_count": len(lines),
        "utility_count": len(utilities),
        "region_count": substations["Region"].nunique(),
        "top_region": profile.index[0],
        "top_region_substations": int(profile.iloc[0]["Substations"]),
        "most_common_voltage": int(substations["Voltage (kV)"].mode().iloc[0]),
        "most_common_voltage_share": round(
            100 * (substations["Voltage (kV)"] ==
                   substations["Voltage (kV)"].mode().iloc[0]).mean(), 1),
        "top_utility": footprint.iloc[0]["Alias"],
        "top_utility_lines": int(footprint.iloc[0]["Lines Operated"]),
        "most_connected": connectivity.iloc[0]["Short Name"],
        "most_connected_degree": int(connectivity.iloc[0]["Connections"]),
        "mean_degree": round(2 * len(lines) / len(substations), 2),
        "isolated_substations": int(len(isolated)),
        "isolated_names": ", ".join(isolated["Short Name"].tolist()) or "none",
        "inactive_substations": int(len(inactive)),
        "inactive_share": round(100 * len(inactive) / len(substations), 1),
        "maintenance_lines": int(len(maintenance)),
        "maintenance_share": round(100 * len(maintenance) / len(lines), 1),
        "total_capacity": round(total_capacity, 1),
        "top5_capacity_share": round(100 * top5_capacity["Capacity (MVA)"].sum()
                                     / total_capacity, 1),
        "mean_line_length": round(lines["Length (km)"].mean(), 1),
        "median_line_length": round(lines["Length (km)"].median(), 1),
        "max_line_length": round(lines["Length (km)"].max(), 1),
        "cross_border_substations": int(len(cross_border)),
        "oldest_year": int(substations["Commissioning Year"].min()),
        "newest_year": int(substations["Commissioning Year"].max()),
        "oldest_region": profile["Median Commissioning Year"].idxmin(),
        "oldest_region_year": int(profile["Median Commissioning Year"].min()),
        "underground_share": round(
            100 * (lines["Line Type"] == "Underground").mean(), 1),
    }
    return findings

def write_report(findings, frequencies, footprint, connectivity, profile):
    f = findings
    md = ["# Task 1.2 Exploratory Data Analysis Report", ""]
    md.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    md.append("")
    md.append("## 1. Dataset scale")
    md.append("")
    md.append(f"- {f['substation_count']} substations across {f['region_count']} regions "
              f"and border locations")
    md.append(f"- {f['line_count']} transmission and distribution lines")
    md.append(f"- {f['utility_count']} utilities, of which "
              f"{int(frequencies['utility_active'].get('Y', 0))} are active")
    md.append(f"- {f['cross_border_substations']} substations sit outside Ghana and represent "
              f"WAPP interconnection points")
    md.append("")
    md.append("## 2. Geographic distribution")
    md.append("")
    md.append(f"- {f['top_region']} holds the largest number of substations "
              f"({f['top_region_substations']})")
    md.append(f"- Median commissioning year is lowest in {f['oldest_region']} "
              f"({f['oldest_region_year']}), making it the oldest regional asset base")
    md.append(f"- Commissioning years span {f['oldest_year']} to {f['newest_year']}")
    md.append("")
    md.append("### Regional profile")
    md.append("")
    md.append(to_md(profile, index=True, index_label="Region"))
    md.append("")
    md.append("## 3. Asset characteristics")
    md.append("")
    md.append(f"- {f['most_common_voltage']} kV is the most common substation voltage "
              f"({f['most_common_voltage_share']}% of substations)")
    md.append(f"- Total installed substation capacity is {f['total_capacity']} MVA")
    md.append(f"- The five largest substations hold {f['top5_capacity_share']}% of total capacity")
    md.append(f"- {f['underground_share']}% of lines are underground")
    md.append(f"- Line length averages {f['mean_line_length']} km "
              f"(median {f['median_line_length']} km, maximum {f['max_line_length']} km)")
    md.append("")
    md.append("## 4. Operational status")
    md.append("")
    md.append(f"- {f['inactive_substations']} substations are Inactive "
              f"({f['inactive_share']}% of the estate)")
    md.append(f"- {f['maintenance_lines']} lines are Under Maintenance "
              f"({f['maintenance_share']}% of all lines)")
    md.append("")
    md.append("## 5. Connectivity")
    md.append("")
    md.append(f"- {f['most_connected']} is the most-connected substation with "
              f"{f['most_connected_degree']} lines")
    md.append(f"- Mean connections per substation is {f['mean_degree']}")
    md.append(f"- {f['isolated_substations']} substations have no lines at all "
              f"({f['isolated_names']})")
    md.append("")
    md.append("### Top 10 substations by connections")
    md.append("")
    md.append(to_md(connectivity.head(10)[
        ["Short Name", "Region", "Voltage (kV)", "Capacity (MVA)", "Status",
         "Connections"]], index=False))
    md.append("")
    md.append("### Utilities by lines operated")
    md.append("")
    md.append(to_md(footprint[["Alias", "Type", "Country", "Lines Operated",
                              "Total Length (km)"]], index=False))
    md.append("")
    md.append("## 6. Initial hypotheses about network structure")
    md.append("")
    md.append(f"- H1: The network is hub-dominated. {f['most_connected']} carries "
              f"{f['most_connected_degree']} lines against a mean of {f['mean_degree']}, so "
              f"degree distribution is expected to be right-skewed rather than uniform.")
    md.append("- H2: Regional clustering will dominate community detection, because most lines "
              "are drawn within a region and only a small backbone crosses regional boundaries.")
    md.append("- H3: The regional hub substations that terminate the backbone lines will show "
              "high betweenness centrality relative to their degree, making them candidate "
              "single points of failure for the N-1 analysis in Week 3.")
    md.append(f"- H4: Capacity is concentrated. With {f['top5_capacity_share']}% of MVA in five "
              f"substations, capacity-weighted criticality will rank differently from a "
              f"purely topological ranking.")
    md.append("- H5: Cross-border WAPP nodes attach to the network through very few lines, so "
              "their removal should disconnect neighbouring-country nodes rather than "
              "fragment the Ghanaian core.")
    md.append("")
    md.append("## 7. Patterns worth further investigation")
    md.append("")
    md.append("- Whether high-degree substations are also high-capacity, or whether "
              "connectivity and capacity are decoupled in this dataset.")
    md.append("- Whether older regions carry a higher share of lines Under Maintenance, which "
              "would support using asset age as a reliability proxy.")
    md.append("- Whether the backbone lines rated at 330 kV terminate at substations rated "
              "below 330 kV, which the Task 1.1 quality checks flagged as a consistency issue.")
    md.append("- How line length relates to voltage tier, and whether long runs are "
              "concentrated in the sparsely served northern regions.")
    md.append("- Whether any region depends on a single line for its connection to the rest "
              "of the grid.")
    md.append("")
    md.append("## 8. Outputs")
    md.append("")
    md.append("- Figures: `figures/*.png`")
    md.append("- Tables: `reports/eda_tables/*.csv`")
    md.append("")
    (REPORTS / "eda_report.md").write_text("\n".join(md), encoding="utf-8")

def main():
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    utilities, substations, lines = load_clean()

    tables = descriptive_statistics(utilities, substations, lines)
    frequencies = frequency_distributions(utilities, substations, lines)
    footprint = utility_footprint(utilities, lines)
    connectivity = substation_connectivity(substations, lines)
    profile, lines_with_regions = regional_profile(substations, lines)
    build_figures(utilities, substations, lines, footprint, connectivity, profile,
                  lines_with_regions)
    findings = build_findings(utilities, substations, lines, footprint, connectivity, profile)
    write_report(findings, frequencies, footprint, connectivity, profile)
    print("Substations numeric summary")
    print(tables["substations_numeric"].round(2))
    print("\nLines numeric summary")
    print(tables["lines_numeric"].round(2))
    print("\nSubstations by region")
    print(frequencies["substation_region"])
    print("\nSubstation status")
    print(frequencies["substation_status"])
    print("\nVoltage levels")
    print(frequencies["substation_voltage"])
    print("\nTop 10 most-connected substations")
    print(connectivity.head(10)[["Short Name", "Region", "Connections"]])
    print("\nUtilities by lines operated")
    print(footprint[["Alias", "Lines Operated"]])
    print(f"\nFigures: {FIGURES}")
    print(f"Tables: {TABLES}")
    print(f"Report: {REPORTS / 'eda_report.md'}")
    return findings

if __name__ == "__main__":
    main()
