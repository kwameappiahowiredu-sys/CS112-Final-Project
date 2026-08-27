from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent
CLEAN_DATA_DIR = PROJECT_DIR / "data" / "clean"
REPORTS_DIR = PROJECT_DIR / "reports"
EDA_TABLES_DIR = REPORTS_DIR / "eda_tables"
FIGURES_DIR = PROJECT_DIR / "figures"

plt.rcParams["figure.autolayout"] = True
plt.rcParams["axes.grid"] = True
plt.rcParams["grid.alpha"] = 0.3


def load_clean():
    utilities = pd.read_csv(CLEAN_DATA_DIR / "utilities_clean.csv")
    substations = pd.read_csv(CLEAN_DATA_DIR / "substations_clean.csv")
    lines = pd.read_csv(CLEAN_DATA_DIR / "lines_clean.csv")
    return utilities, substations, lines


def save_table(dataframe, name):
    dataframe.to_csv(EDA_TABLES_DIR / f"{name}.csv", index=True)


def to_md(dataframe, index=True, index_label=""):
    frame = dataframe.reset_index() if index else dataframe
    if index and index_label:
        frame = frame.rename(columns={frame.columns[0]: index_label})
    headers = [str(column) for column in frame.columns]
    markdown_rows = ["| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |"]
    for values in frame.itertuples(index=False):
        markdown_rows.append("| " + " | ".join(
            f"{value:g}" if isinstance(value, float) else str(value)
            for value in values) + " |")
    return "\n".join(markdown_rows)


def bar_chart(series, title, x_label, y_label, filename, rotation=45, color="#1f77b4"):
    figure, axes = plt.subplots(figsize=(10, 6))
    series.plot(kind="bar", ax=axes, color=color, edgecolor="black", linewidth=0.4)
    axes.set_title(title)
    axes.set_xlabel(x_label)
    axes.set_ylabel(y_label)
    plt.setp(axes.get_xticklabels(), rotation=rotation, ha="right" if rotation else "center")
    figure.savefig(FIGURES_DIR / filename, dpi=150)
    plt.close(figure)


def histogram(values, bins, title, x_label, y_label, filename, color="#2ca02c"):
    figure, axes = plt.subplots(figsize=(10, 6))
    axes.hist(values.dropna(), bins=bins, color=color, edgecolor="black", linewidth=0.4)
    axes.set_title(title)
    axes.set_xlabel(x_label)
    axes.set_ylabel(y_label)
    figure.savefig(FIGURES_DIR / filename, dpi=150)
    plt.close(figure)


def stacked_chart(frame, title, x_label, y_label, filename, rotation=45):
    figure, axes = plt.subplots(figsize=(10, 6))
    frame.plot(kind="bar", stacked=True, ax=axes, edgecolor="black", linewidth=0.4)
    axes.set_title(title)
    axes.set_xlabel(x_label)
    axes.set_ylabel(y_label)
    axes.legend(title=frame.columns.name or "")
    plt.setp(axes.get_xticklabels(), rotation=rotation, ha="right" if rotation else "center")
    figure.savefig(FIGURES_DIR / filename, dpi=150)
    plt.close(figure)


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
    line_counts = lines["Utility ID"].value_counts().rename("Lines Operated")
    utility_summary = utilities.set_index("Utility ID")[["Name", "Alias", "Type", "Country"]].join(
        line_counts, how="left")
    utility_summary["Lines Operated"] = utility_summary["Lines Operated"].fillna(0).astype(int)
    utility_summary["Total Length (km)"] = lines.groupby("Utility ID")["Length (km)"].sum().round(1)
    utility_summary["Total Length (km)"] = utility_summary["Total Length (km)"].fillna(0)
    utility_summary["Mean Line Capacity (MVA)"] = (
        lines.groupby("Utility ID")["Capacity (MVA)"].mean().round(1))
    utility_summary = utility_summary.sort_values("Lines Operated", ascending=False)
    save_table(utility_summary, "utility_footprint")
    return utility_summary


def substation_connectivity(substations, lines):
    line_endpoints = pd.concat([lines["Source Substation ID"], lines["Destination Substation ID"]])
    connection_counts = line_endpoints.value_counts().rename("Connections")
    substation_summary = substations.set_index("Substation ID")[
        ["Name", "Short Name", "Region", "Country", "Voltage (kV)", "Capacity (MVA)",
         "Type", "Status"]].join(connection_counts, how="left")
    substation_summary["Connections"] = substation_summary["Connections"].fillna(0).astype(int)
    substation_summary = substation_summary.sort_values("Connections", ascending=False)
    save_table(substation_summary, "substation_connectivity")
    return substation_summary


def regional_profile(substations, lines):
    region_lookup = substations.set_index("Substation ID")["Region"]
    lines = lines.copy()
    lines["Source Region"] = lines["Source Substation ID"].map(region_lookup)
    lines["Destination Region"] = lines["Destination Substation ID"].map(region_lookup)
    lines["Inter-Regional"] = lines["Source Region"] != lines["Destination Region"]

    regional_summary = pd.DataFrame({
        "Substations": substations.groupby("Region").size(),
        "Total Capacity (MVA)": substations.groupby("Region")["Capacity (MVA)"].sum().round(1),
        "Mean Capacity (MVA)": substations.groupby("Region")["Capacity (MVA)"].mean().round(1),
        "Median Commissioning Year": substations.groupby("Region")["Commissioning Year"].median(),
        "Active Substations": substations[substations["Status"] == "Active"].groupby("Region").size(),
    })
    regional_summary["Active Substations"] = regional_summary["Active Substations"].fillna(0).astype(int)

    internal_line_counts = lines[~lines["Inter-Regional"]].groupby("Source Region").size()
    outgoing_line_counts = lines[lines["Inter-Regional"]].groupby("Source Region").size()
    incoming_line_counts = lines[lines["Inter-Regional"]].groupby("Destination Region").size()
    regional_summary["Internal Lines"] = internal_line_counts.reindex(regional_summary.index).fillna(0).astype(int)
    regional_summary["Inter-Regional Lines"] = (
        outgoing_line_counts.reindex(regional_summary.index).fillna(0)
        + incoming_line_counts.reindex(regional_summary.index).fillna(0)).astype(int)
    regional_summary = regional_summary.sort_values("Substations", ascending=False)
    save_table(regional_summary, "regional_profile")

    interregional_flows = lines[lines["Inter-Regional"]].groupby(
        ["Source Region", "Destination Region"]).size().rename("Lines").sort_values(
        ascending=False).to_frame()
    save_table(interregional_flows, "inter_regional_flows")
    return regional_summary, lines


def build_figures(utilities, substations, lines, utility_summary, substation_summary, regional_summary,
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
              "Number of Substations",
              "06_commissioning_year_distribution.png",
              color="#d62728")

    bar_chart(substation_summary.head(10).set_index("Short Name")["Connections"],
              "Top 10 Most-Connected Substations", "Substation", "Number of Lines",
              "07_top_connected_substations.png", color="#17becf")

    bar_chart(utility_summary.set_index("Alias")["Lines Operated"],
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

    bar_chart(regional_summary["Mean Capacity (MVA)"],
              "Mean Substation Capacity by Region", "Region", "Mean Capacity (MVA)",
              "11_mean_capacity_by_region.png", color="#e377c2")

    bar_chart(regional_summary["Median Commissioning Year"],
              "Median Commissioning Year by Region", "Region", "Median Commissioning Year",
              "12_median_commissioning_year_by_region.png", color="#bcbd22")

    return status_by_utility


def build_findings(utilities, substations, lines, utility_summary, substation_summary, regional_summary):
    total_capacity = substations["Capacity (MVA)"].sum()
    top_five_capacity = substation_summary.sort_values("Capacity (MVA)", ascending=False).head(5)
    isolated_substations = substation_summary[substation_summary["Connections"] == 0]
    maintenance_lines = lines[lines["Status"] == "Under Maintenance"]
    inactive_substations = substations[substations["Status"] == "Inactive"]
    cross_border_substations = substations[substations["Country"] != "Ghana"]

    findings = {
        "substation_count": len(substations),
        "line_count": len(lines),
        "utility_count": len(utilities),
        "region_count": substations["Region"].nunique(),
        "top_region": regional_summary.index[0],
        "top_region_substations": int(regional_summary.iloc[0]["Substations"]),
        "most_common_voltage": int(substations["Voltage (kV)"].mode().iloc[0]),
        "most_common_voltage_share": round(
            100 * (substations["Voltage (kV)"] ==
                   substations["Voltage (kV)"].mode().iloc[0]).mean(), 1),
        "top_utility": utility_summary.iloc[0]["Alias"],
        "top_utility_lines": int(utility_summary.iloc[0]["Lines Operated"]),
        "most_connected": substation_summary.iloc[0]["Short Name"],
        "most_connected_degree": int(substation_summary.iloc[0]["Connections"]),
        "mean_degree": round(2 * len(lines) / len(substations), 2),
        "isolated_substations": int(len(isolated_substations)),
        "isolated_names": ", ".join(isolated_substations["Short Name"].tolist()) or "none",
        "inactive_substations": int(len(inactive_substations)),
        "inactive_share": round(100 * len(inactive_substations) / len(substations), 1),
        "maintenance_lines": int(len(maintenance_lines)),
        "maintenance_share": round(100 * len(maintenance_lines) / len(lines), 1),
        "total_capacity": round(total_capacity, 1),
        "top5_capacity_share": round(100 * top_five_capacity["Capacity (MVA)"].sum()
                                     / total_capacity, 1),
        "mean_line_length": round(lines["Length (km)"].mean(), 1),
        "median_line_length": round(lines["Length (km)"].median(), 1),
        "max_line_length": round(lines["Length (km)"].max(), 1),
        "cross_border_substations": int(len(cross_border_substations)),
        "oldest_year": int(substations["Commissioning Year"].min()),
        "newest_year": int(substations["Commissioning Year"].max()),
        "oldest_region": regional_summary["Median Commissioning Year"].idxmin(),
        "oldest_region_year": int(regional_summary["Median Commissioning Year"].min()),
        "underground_share": round(
            100 * (lines["Line Type"] == "Underground").mean(), 1),
    }
    return findings


def write_report(findings, frequencies, utility_summary, substation_summary, regional_summary):
    summary_findings = findings
    report_lines = ["# Task 1.2 Exploratory Data Analysis Report", ""]
    report_lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    report_lines.append("")
    report_lines.append("## 1. Dataset scale")
    report_lines.append("")
    report_lines.append(f"- {summary_findings['substation_count']} substations across {summary_findings['region_count']} regions "
              f"and border locations")
    report_lines.append(f"- {summary_findings['line_count']} transmission and distribution lines")
    report_lines.append(f"- {summary_findings['utility_count']} utilities, of which "
              f"{int(frequencies['utility_active'].get('Y', 0))} are active")
    report_lines.append(f"- {summary_findings['cross_border_substations']} substations sit outside Ghana and represent "
              f"WAPP interconnection points")
    report_lines.append("")
    report_lines.append("## 2. Geographic distribution")
    report_lines.append("")
    report_lines.append(f"- {summary_findings['top_region']} holds the largest number of substations "
              f"({summary_findings['top_region_substations']})")
    report_lines.append(f"- Median commissioning year is lowest in {summary_findings['oldest_region']} "
              f"({summary_findings['oldest_region_year']}), making it the oldest regional asset base")
    report_lines.append(f"- Commissioning years span {summary_findings['oldest_year']} to {summary_findings['newest_year']}")
    report_lines.append("")
    report_lines.append("### Regional profile")
    report_lines.append("")
    report_lines.append(to_md(regional_summary, index=True, index_label="Region"))
    report_lines.append("")
    report_lines.append("## 3. Asset characteristics")
    report_lines.append("")
    report_lines.append(f"- {summary_findings['most_common_voltage']} kV is the most common substation voltage "
              f"({summary_findings['most_common_voltage_share']}% of substations)")
    report_lines.append(f"- Total installed substation capacity is {summary_findings['total_capacity']} MVA")
    report_lines.append(f"- The five largest substations hold {summary_findings['top5_capacity_share']}% of total capacity")
    report_lines.append(f"- {summary_findings['underground_share']}% of lines are underground")
    report_lines.append(f"- Line length averages {summary_findings['mean_line_length']} km "
              f"(median {summary_findings['median_line_length']} km, maximum {summary_findings['max_line_length']} km)")
    report_lines.append("")
    report_lines.append("## 4. Operational status")
    report_lines.append("")
    report_lines.append(f"- {summary_findings['inactive_substations']} substations are Inactive "
              f"({summary_findings['inactive_share']}% of the estate)")
    report_lines.append(f"- {summary_findings['maintenance_lines']} lines are Under Maintenance "
              f"({summary_findings['maintenance_share']}% of all lines)")
    report_lines.append("")
    report_lines.append("## 5. Connectivity")
    report_lines.append("")
    report_lines.append(f"- {summary_findings['most_connected']} is the most-connected substation with "
              f"{summary_findings['most_connected_degree']} lines")
    report_lines.append(f"- Mean connections per substation is {summary_findings['mean_degree']}")
    report_lines.append(f"- {summary_findings['isolated_substations']} substations have no lines at all "
              f"({summary_findings['isolated_names']})")
    report_lines.append("")
    report_lines.append("### Top 10 substations by connections")
    report_lines.append("")
    report_lines.append(to_md(substation_summary.head(10)[
        ["Short Name", "Region", "Voltage (kV)", "Capacity (MVA)", "Status",
         "Connections"]], index=False))
    report_lines.append("")
    report_lines.append("### Utilities by lines operated")
    report_lines.append("")
    report_lines.append(to_md(utility_summary[["Alias", "Type", "Country", "Lines Operated",
                              "Total Length (km)"]], index=False))
    report_lines.append("")
    report_lines.append("## 6. Initial hypotheses about network structure")
    report_lines.append("")
    report_lines.append(f"- H1: The network is hub-dominated. {summary_findings['most_connected']} carries "
              f"{summary_findings['most_connected_degree']} lines against a mean of {summary_findings['mean_degree']}, so "
              f"degree distribution is expected to be right-skewed rather than uniform.")
    report_lines.append("- H2: Regional clustering will dominate community detection, because most lines "
              "are drawn within a region and only a small backbone crosses regional boundaries.")
    report_lines.append("- H3: The regional hub substations that terminate the backbone lines will show "
              "high betweenness centrality relative to their degree, making them candidate "
              "single points of failure for the N-1 analysis in Week 3.")
    report_lines.append(f"- H4: Capacity is concentrated. With {summary_findings['top5_capacity_share']}% of MVA in five "
              f"substations, capacity-weighted criticality will rank differently from a "
              f"purely topological ranking.")
    report_lines.append("- H5: Cross-border WAPP nodes attach to the network through very few lines, so "
              "their removal should disconnect neighbouring-country nodes rather than "
              "fragment the Ghanaian core.")
    report_lines.append("")
    report_lines.append("## 7. Patterns worth further investigation")
    report_lines.append("")
    report_lines.append("- Whether high-degree substations are also high-capacity, or whether "
              "connectivity and capacity are decoupled in this dataset.")
    report_lines.append("- Whether older regions carry a higher share of lines Under Maintenance, which "
              "would support using asset age as a reliability proxy.")
    report_lines.append("- Whether the backbone lines rated at 330 kV terminate at substations rated "
              "below 330 kV, which the Task 1.1 quality checks flagged as a consistency issue.")
    report_lines.append("- How line length relates to voltage tier, and whether long runs are "
              "concentrated in the sparsely served northern regions.")
    report_lines.append("- Whether any region depends on a single line for its connection to the rest "
              "of the grid.")
    report_lines.append("")
    report_lines.append("## 8. Outputs")
    report_lines.append("")
    report_lines.append("- Figures: `figures/*.png`")
    report_lines.append("- Tables: `reports/eda_tables/*.csv`")
    report_lines.append("")
    (REPORTS_DIR / "eda_report.md").write_text("\n".join(report_lines), encoding="utf-8")


def main():
    EDA_TABLES_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    utilities, substations, lines = load_clean()

    tables = descriptive_statistics(utilities, substations, lines)
    frequencies = frequency_distributions(utilities, substations, lines)
    utility_summary = utility_footprint(utilities, lines)
    substation_summary = substation_connectivity(substations, lines)
    regional_summary, lines_with_regions = regional_profile(substations, lines)
    build_figures(utilities, substations, lines, utility_summary, substation_summary, regional_summary,
                  lines_with_regions)
    findings = build_findings(utilities, substations, lines, utility_summary, substation_summary, regional_summary)
    write_report(findings, frequencies, utility_summary, substation_summary, regional_summary)

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
    print(substation_summary.head(10)[["Short Name", "Region", "Connections"]])
    print("\nUtilities by lines operated")
    print(utility_summary[["Alias", "Lines Operated"]])
    print(f"\nFigures: {FIGURES_DIR}")
    print(f"Tables: {EDA_TABLES_DIR}")
    print(f"Report: {REPORTS_DIR / 'eda_report.md'}")
    return findings


if __name__ == "__main__":
    main()
