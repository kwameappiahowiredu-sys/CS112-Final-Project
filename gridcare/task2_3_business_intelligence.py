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
TABLES = REPORTS / "bi_tables"
NETWORK_TABLES = REPORTS / "network_tables"
GEO_TABLES = REPORTS / "geo_tables"
FIGURES = BASE / "figures"

CURRENT_YEAR = datetime.now().year
AGE_BANDS = [(0, 10, "Under 10 years"), (10, 25, "10 to 24 years"),
             (25, 40, "25 to 39 years"), (40, 200, "40 years and over")]
UTILISATION_BANDS = [(1.5, "Over-subscribed"), (0.5, "Balanced"), (0.0, "Under-provisioned")]
AGEING_THRESHOLD_YEARS = 40
REFERENCE_VOLTAGE_KV = 330.0

RISK_WEIGHTS = {
    "maintenance_share": 0.25,
    "mean_age": 0.25,
    "capacity_concentration": 0.20,
    "bridge_dependency": 0.30,
}

plt.rcParams["figure.autolayout"] = True
plt.rcParams["axes.grid"] = True
plt.rcParams["grid.alpha"] = 0.3


def load_clean():
    utilities = pd.read_csv(CLEAN / "utilities_clean.csv")
    substations = pd.read_csv(CLEAN / "substations_clean.csv")
    lines = pd.read_csv(CLEAN / "lines_clean.csv")
    return utilities, substations, lines


def load_optional(path):
    return pd.read_csv(path) if path.exists() else None


def to_md(df, index=False, index_label=""):
    frame = df.reset_index() if index else df
    if index and index_label:
        frame = frame.rename(columns={frame.columns[0]: index_label})
    headers = [str(column) for column in frame.columns]
    rows = ["| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |"]
    for values in frame.itertuples(index=False):
        rows.append("| " + " | ".join(
            f"{value:g}" if isinstance(value, float) else str(value)
            for value in values) + " |")
    return "\n".join(rows)


def normalise(series):
    span = series.max() - series.min()
    if span == 0 or span != span:
        return pd.Series(0.0, index=series.index)
    return (series - series.min()) / span


def annotate_lines(substations, lines):
    lookup = substations.set_index("Substation ID")[["Region", "Country", "Short Name"]]
    source = lookup.reindex(lines["Source Substation ID"].values)
    destination = lookup.reindex(lines["Destination Substation ID"].values)

    frame = lines.copy()
    frame["Source Region"] = source["Region"].values
    frame["Destination Region"] = destination["Region"].values
    frame["Source Name"] = source["Short Name"].values
    frame["Destination Name"] = destination["Short Name"].values
    frame["Inter-Regional"] = frame["Source Region"] != frame["Destination Region"]
    frame["Under Maintenance"] = frame["Status"] == "Under Maintenance"
    frame["Loss Index"] = np.round(
        frame["Length (km)"] * (REFERENCE_VOLTAGE_KV / frame["Voltage (kV)"]) ** 2, 1)
    return frame


def annotate_substations(substations, annotated_lines):
    endpoints = pd.concat([
        annotated_lines[["Source Substation ID", "Capacity (MVA)", "Length (km)",
                         "Under Maintenance", "Loss Index"]].rename(
            columns={"Source Substation ID": "Substation ID",
                     "Capacity (MVA)": "Line Capacity (MVA)"}),
        annotated_lines[["Destination Substation ID", "Capacity (MVA)", "Length (km)",
                         "Under Maintenance", "Loss Index"]].rename(
            columns={"Destination Substation ID": "Substation ID",
                     "Capacity (MVA)": "Line Capacity (MVA)"}),
    ], ignore_index=True)

    grouped = endpoints.groupby("Substation ID")
    summary = pd.DataFrame({
        "Incident Lines": grouped.size(),
        "Incident Line Capacity (MVA)": grouped["Line Capacity (MVA)"].sum().round(1),
        "Incident Line Length (km)": grouped["Length (km)"].sum().round(1),
        "Incident Lines Under Maintenance": grouped["Under Maintenance"].sum().astype(int),
        "Incident Loss Index": grouped["Loss Index"].sum().round(1),
    })

    frame = substations.set_index("Substation ID").join(summary, how="left")
    for column in ["Incident Lines", "Incident Lines Under Maintenance"]:
        frame[column] = frame[column].fillna(0).astype(int)
    for column in ["Incident Line Capacity (MVA)", "Incident Line Length (km)",
                   "Incident Loss Index"]:
        frame[column] = frame[column].fillna(0.0)

    frame["Asset Age (years)"] = CURRENT_YEAR - frame["Commissioning Year"]
    frame["Capacity Utilisation"] = (
        frame["Incident Line Capacity (MVA)"] / frame["Capacity (MVA)"]).round(2)

    def band_age(age):
        for low, high, label in AGE_BANDS:
            if low <= age < high:
                return label
        return AGE_BANDS[-1][2]

    def band_utilisation(ratio):
        for threshold, label in UTILISATION_BANDS:
            if ratio >= threshold:
                return label
        return UTILISATION_BANDS[-1][1]

    frame["Age Band"] = frame["Asset Age (years)"].apply(band_age)
    frame["Utilisation Band"] = frame["Capacity Utilisation"].apply(band_utilisation)
    return frame.reset_index()


def utility_footprint(utilities, annotated_lines):
    records = []
    for utility_id, group in annotated_lines.groupby("Utility ID"):
        details = utilities[utilities["Utility ID"] == utility_id]
        touched = set(group["Source Substation ID"]).union(group["Destination Substation ID"])
        regions = set(group["Source Region"]).union(group["Destination Region"])
        records.append({
            "Utility ID": utility_id,
            "Alias": details["Alias"].iloc[0] if len(details) else str(utility_id),
            "Type": details["Type"].iloc[0] if len(details) else "",
            "Country": details["Country"].iloc[0] if len(details) else "",
            "Lines": len(group),
            "Substations Touched": len(touched),
            "Regions Served": len(regions),
            "Total Length (km)": round(group["Length (km)"].sum(), 1),
            "Total Line Capacity (MVA)": round(group["Capacity (MVA)"].sum(), 1),
            "Inter-Regional Lines": int(group["Inter-Regional"].sum()),
            "Lines Under Maintenance": int(group["Under Maintenance"].sum()),
            "Maintenance Share %": round(100 * group["Under Maintenance"].mean(), 1),
            "Total Loss Index": round(group["Loss Index"].sum(), 1),
            "Loss Index per km": round(
                group["Loss Index"].sum() / group["Length (km)"].sum(), 2)
            if group["Length (km)"].sum() > 0 else np.nan,
        })
    footprint = pd.DataFrame(records).sort_values("Total Length (km)", ascending=False)

    idle = utilities[~utilities["Utility ID"].isin(annotated_lines["Utility ID"])]
    by_region = pd.crosstab(annotated_lines["Utility ID"], annotated_lines["Source Region"])
    by_voltage = pd.crosstab(annotated_lines["Utility ID"], annotated_lines["Voltage (kV)"])
    alias = dict(zip(utilities["Utility ID"], utilities["Alias"]))
    by_region.index = [alias.get(index, index) for index in by_region.index]
    by_voltage.index = [alias.get(index, index) for index in by_voltage.index]
    return footprint.reset_index(drop=True), idle, by_region, by_voltage


def capacity_analysis(annotated_substations, ranking):
    frame = annotated_substations.copy()
    connected = frame[frame["Incident Lines"] > 0]

    upgrade = connected.sort_values("Capacity Utilisation", ascending=False).head(12)[
        ["Substation ID", "Short Name", "Region", "Voltage (kV)", "Capacity (MVA)",
         "Incident Line Capacity (MVA)", "Incident Lines", "Capacity Utilisation",
         "Asset Age (years)", "Status"]].copy()

    if ranking is not None and "Substation ID" in ranking.columns:
        tiers = dict(zip(ranking["Substation ID"], ranking["Criticality Tier"]))
        upgrade["Criticality Tier"] = upgrade["Substation ID"].map(tiers).fillna("Unranked")
    upgrade = upgrade.drop(columns=["Substation ID"])

    bands = frame.groupby("Utilisation Band").agg(
        Substations=("Substation ID", "count"),
        Mean_Utilisation=("Capacity Utilisation", "mean"),
        Total_Capacity=("Capacity (MVA)", "sum")).round(2)
    bands.columns = ["Substations", "Mean Utilisation", "Total Capacity (MVA)"]

    total_capacity = frame["Capacity (MVA)"].sum()
    shares = (frame["Capacity (MVA)"] / total_capacity).sort_values(ascending=False)
    concentration = {
        "Total capacity (MVA)": round(total_capacity, 1),
        "Top 5 substations share %": round(100 * shares.head(5).sum(), 1),
        "Top 10 substations share %": round(100 * shares.head(10).sum(), 1),
        "Herfindahl-Hirschman Index": round(float((shares ** 2).sum() * 10000), 1),
        "Mean capacity (MVA)": round(frame["Capacity (MVA)"].mean(), 1),
        "Median capacity (MVA)": round(frame["Capacity (MVA)"].median(), 1),
    }
    return upgrade.reset_index(drop=True), bands, concentration, shares


def age_profile(annotated_substations):
    frame = annotated_substations
    bands = frame.groupby("Age Band").agg(
        Substations=("Substation ID", "count"),
        Mean_Age=("Asset Age (years)", "mean"),
        Total_Capacity=("Capacity (MVA)", "sum")).round(1)
    bands.columns = ["Substations", "Mean Age (years)", "Total Capacity (MVA)"]

    by_region = frame.groupby("Region").agg(
        Substations=("Substation ID", "count"),
        Mean_Age=("Asset Age (years)", "mean"),
        Median_Age=("Asset Age (years)", "median"),
        Oldest=("Asset Age (years)", "max"),
        Ageing_Assets=("Asset Age (years)",
                       lambda values: int((values >= AGEING_THRESHOLD_YEARS).sum()))).round(1)
    by_region.columns = ["Substations", "Mean Age (years)", "Median Age (years)",
                         "Oldest Asset (years)", f"Assets over {AGEING_THRESHOLD_YEARS} years"]
    by_region = by_region.sort_values("Mean Age (years)", ascending=False)

    by_type = frame.groupby("Type").agg(
        Substations=("Substation ID", "count"),
        Mean_Age=("Asset Age (years)", "mean"),
        Mean_Capacity=("Capacity (MVA)", "mean")).round(1)
    by_type.columns = ["Substations", "Mean Age (years)", "Mean Capacity (MVA)"]

    oldest = frame.sort_values("Asset Age (years)", ascending=False).head(10)[
        ["Short Name", "Region", "Type", "Voltage (kV)", "Capacity (MVA)",
         "Commissioning Year", "Asset Age (years)", "Incident Lines", "Status"]]
    return bands, by_region, by_type, oldest.reset_index(drop=True)


def reliability_analysis(annotated_lines, annotated_substations, bridges):
    by_region_source = annotated_lines.groupby("Source Region").agg(
        Lines=("Line ID", "count"),
        Under_Maintenance=("Under Maintenance", "sum"),
        Total_Length=("Length (km)", "sum"),
        Loss_Index=("Loss Index", "sum"))
    by_region_source.columns = ["Lines", "Lines Under Maintenance", "Total Length (km)",
                                "Loss Index"]
    by_region_source["Maintenance Share %"] = (
        100 * by_region_source["Lines Under Maintenance"]
        / by_region_source["Lines"]).round(1)

    substation_region = annotated_substations.groupby("Region").agg(
        Substations=("Substation ID", "count"),
        Mean_Age=("Asset Age (years)", "mean"),
        Total_Capacity=("Capacity (MVA)", "sum"),
        Inactive=("Status", lambda values: int((values != "Active").sum())))
    substation_region.columns = ["Substations", "Mean Age (years)",
                                 "Total Capacity (MVA)", "Inactive Substations"]

    profile = substation_region.join(by_region_source, how="left")
    for column in ["Lines", "Lines Under Maintenance"]:
        profile[column] = profile[column].fillna(0).astype(int)
    for column in ["Total Length (km)", "Loss Index", "Maintenance Share %"]:
        profile[column] = profile[column].fillna(0.0)

    capacity_share = (annotated_substations.groupby("Region")["Capacity (MVA)"]
                      .apply(lambda values: float(
                          ((values / values.sum()) ** 2).sum())))
    profile["Capacity Concentration"] = capacity_share.round(3)

    if bridges is not None and len(bridges):
        bridge_counts = pd.concat([
            bridges.groupby("Source Region").size(),
            bridges.groupby("Destination Region").size()], axis=1).fillna(0).sum(axis=1)
        profile["Bridge Lines"] = bridge_counts.reindex(profile.index).fillna(0).astype(int)
    else:
        profile["Bridge Lines"] = 0
    profile["Bridge Dependency %"] = np.where(
        profile["Lines"] > 0, (100 * profile["Bridge Lines"] / profile["Lines"]).round(1), 0.0)

    components = {
        "maintenance_share": normalise(profile["Maintenance Share %"]),
        "mean_age": normalise(profile["Mean Age (years)"]),
        "capacity_concentration": normalise(profile["Capacity Concentration"]),
        "bridge_dependency": normalise(pd.Series(profile["Bridge Dependency %"].values,
                                                 index=profile.index)),
    }
    score = sum(RISK_WEIGHTS[name] * values for name, values in components.items())
    profile["Reliability Risk Score"] = score.round(3)
    profile = profile.sort_values("Reliability Risk Score", ascending=False)
    profile["Mean Age (years)"] = profile["Mean Age (years)"].round(1)
    profile["Total Capacity (MVA)"] = profile["Total Capacity (MVA)"].round(1)
    profile["Total Length (km)"] = profile["Total Length (km)"].round(1)
    profile["Loss Index"] = profile["Loss Index"].round(1)
    return profile


def growth_opportunities(reliability, density):
    frame = reliability.copy()
    frame["Capacity per Substation (MVA)"] = (
        frame["Total Capacity (MVA)"] / frame["Substations"]).round(1)
    frame["Lines per Substation"] = np.where(
        frame["Substations"] > 0, (frame["Lines"] / frame["Substations"]).round(2), 0.0)

    if density is not None and "Region" in density.columns:
        spacing = density.set_index("Region")["Mean Nearest Neighbour (km)"]
        frame["Mean Nearest Neighbour (km)"] = spacing.reindex(frame.index)
    else:
        frame["Mean Nearest Neighbour (km)"] = np.nan

    components = {
        "sparse_estate": 1 - normalise(frame["Substations"].astype(float)),
        "low_capacity": 1 - normalise(frame["Capacity per Substation (MVA)"]),
        "thin_connectivity": 1 - normalise(pd.Series(frame["Lines per Substation"].values,
                                                     index=frame.index)),
        "wide_spacing": normalise(frame["Mean Nearest Neighbour (km)"].fillna(
            frame["Mean Nearest Neighbour (km)"].mean())),
    }
    frame["Opportunity Score"] = (
        0.30 * components["sparse_estate"]
        + 0.25 * components["low_capacity"]
        + 0.25 * components["thin_connectivity"]
        + 0.20 * components["wide_spacing"]).round(3)
    columns = ["Substations", "Total Capacity (MVA)", "Capacity per Substation (MVA)",
               "Lines per Substation", "Mean Nearest Neighbour (km)", "Opportunity Score"]
    return frame.sort_values("Opportunity Score", ascending=False)[columns]


def strategic_recommendations(reliability, opportunities, upgrade, oldest, footprint,
                              concentration, ranking, bridges):
    recommendations = []

    top_risk = reliability.head(3)
    for region, row in top_risk.iterrows():
        recommendations.append({
            "Priority": "High",
            "Theme": "Network resilience",
            "Area": region,
            "Finding": (f"Risk score {row['Reliability Risk Score']} driven by "
                        f"{row['Bridge Dependency %']}% bridge dependency, mean asset age "
                        f"{row['Mean Age (years)']} years and "
                        f"{row['Maintenance Share %']}% of lines under maintenance."),
            "Recommended action": ("Study a second circuit or an alternative route for the "
                                   "single-path lines serving this region before any "
                                   "planned outage on them."),
        })

    if ranking is not None and len(ranking):
        critical = ranking[ranking["Criticality Tier"].isin(["Critical", "High"])].head(5)
        for row in critical.to_dict("records"):
            recommendations.append({
                "Priority": "High",
                "Theme": "Critical asset",
                "Area": f"{row['Short Name']} ({row['Region']})",
                "Finding": (f"Criticality rank {row['Rank']} with betweenness "
                            f"{row['Betweenness Centrality']} and "
                            f"{row['Nodes Separated From Core']} substations separated "
                            f"from the core if it is lost."),
                "Recommended action": ("Hold spares and a defined restoration plan for this "
                                       "substation, and avoid concurrent maintenance on it "
                                       "and its adjacent bridge lines."),
            })

    ageing = oldest[oldest["Asset Age (years)"] >= AGEING_THRESHOLD_YEARS]
    if len(ageing):
        recommendations.append({
            "Priority": "Medium",
            "Theme": "Asset renewal",
            "Area": "National",
            "Finding": (f"{len(ageing)} substations in the top-ten oldest list are at least "
                        f"{AGEING_THRESHOLD_YEARS} years old, the oldest being "
                        f"{ageing.iloc[0]['Short Name']} at "
                        f"{ageing.iloc[0]['Asset Age (years)']} years."),
            "Recommended action": ("Bring these assets into a condition-assessment programme "
                                   "and sequence replacement by criticality rather than by "
                                   "age alone."),
        })

    over = upgrade[upgrade["Capacity Utilisation"] > 1.5]
    if len(over):
        recommendations.append({
            "Priority": "Medium",
            "Theme": "Capacity headroom",
            "Area": "National",
            "Finding": (f"{len(over)} of the twelve highest-ratio substations carry "
                        f"incident line capacity above 1.5 times their own rating, led by "
                        f"{over.iloc[0]['Short Name']} at "
                        f"{over.iloc[0]['Capacity Utilisation']} times. Ratios of this size "
                        f"indicate inconsistent rating fields rather than real overload."),
            "Recommended action": ("Reconcile the substation and line rating fields in "
                                   "the register before treating any of these as upgrade "
                                   "candidates. The ratio is currently a data-consistency "
                                   "signal rather than a loading measurement."),
        })

    worst_maintenance = footprint.sort_values("Maintenance Share %", ascending=False)
    if len(worst_maintenance) and worst_maintenance.iloc[0]["Maintenance Share %"] > 0:
        row = worst_maintenance.iloc[0]
        recommendations.append({
            "Priority": "Medium",
            "Theme": "Maintenance backlog",
            "Area": row["Alias"],
            "Finding": (f"{row['Maintenance Share %']}% of this utility's "
                        f"{row['Lines']} lines are under maintenance."),
            "Recommended action": ("Review outage scheduling so that concurrent maintenance "
                                   "does not remove parallel paths at the same time."),
        })

    top_opportunity = opportunities.head(3)
    for region, row in top_opportunity.iterrows():
        recommendations.append({
            "Priority": "Low",
            "Theme": "Growth opportunity",
            "Area": region,
            "Finding": (f"Opportunity score {row['Opportunity Score']} from "
                        f"{int(row['Substations'])} substations, "
                        f"{row['Lines per Substation']} lines per substation and "
                        f"{row['Capacity per Substation (MVA)']} MVA per substation."),
            "Recommended action": ("Test demand growth against this coverage before "
                                   "committing capital; low asset density alone does not "
                                   "prove unmet demand."),
        })

    if concentration["Top 5 substations share %"] > 30:
        recommendations.append({
            "Priority": "Medium",
            "Theme": "Capacity concentration",
            "Area": "National",
            "Finding": (f"The five largest substations hold "
                        f"{concentration['Top 5 substations share %']}% of national "
                        f"capacity, with an HHI of "
                        f"{concentration['Herfindahl-Hirschman Index']}."),
            "Recommended action": ("Treat these sites as strategic assets with the "
                                   "corresponding spares, security and restoration "
                                   "priority."),
        })

    if bridges is not None and len(bridges):
        maintenance_bridges = bridges[bridges["Status"] == "Under Maintenance"]
        if len(maintenance_bridges):
            recommendations.append({
                "Priority": "High",
                "Theme": "Concurrent risk",
                "Area": "National",
                "Finding": (f"{len(maintenance_bridges)} bridge lines are currently under "
                            f"maintenance, so a single-path connection is already degraded."),
                "Recommended action": ("Escalate these to the top of the restoration queue "
                                       "and block further outages on the same corridor."),
            })

    return pd.DataFrame(recommendations)


def figure_capacity_utilisation(annotated_substations, filename):
    connected = annotated_substations[annotated_substations["Incident Lines"] > 0]
    fig, ax = plt.subplots(figsize=(11, 7))
    scatter = ax.scatter(connected["Capacity (MVA)"],
                         connected["Incident Line Capacity (MVA)"],
                         c=connected["Asset Age (years)"], cmap="viridis",
                         s=40 + 20 * connected["Incident Lines"],
                         edgecolor="black", linewidth=0.4)
    limit = max(connected["Capacity (MVA)"].max(),
                connected["Incident Line Capacity (MVA)"].max())
    ax.plot([0, limit], [0, limit], color="#d62728", linestyle="--",
            label="Parity: incident line capacity equals substation rating")
    for record in connected.sort_values("Capacity Utilisation",
                                        ascending=False).head(6).to_dict("records"):
        ax.annotate(record["Short Name"],
                    (record["Capacity (MVA)"], record["Incident Line Capacity (MVA)"]),
                    fontsize=7, xytext=(4, 4), textcoords="offset points")
    ax.set_title("Substation rating against incident line capacity")
    ax.set_xlabel("Substation capacity (MVA)")
    ax.set_ylabel("Incident line capacity (MVA)")
    ax.legend()
    fig.colorbar(scatter, ax=ax, label="Asset age (years)")
    fig.savefig(FIGURES / filename, dpi=150)
    plt.close(fig)


def figure_age_profile(annotated_substations, age_by_region, filename):
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    axes[0].hist(annotated_substations["Asset Age (years)"], bins=12,
                 color="#8c564b", edgecolor="black", linewidth=0.4)
    axes[0].axvline(AGEING_THRESHOLD_YEARS, color="#d62728", linestyle="--",
                    label=f"{AGEING_THRESHOLD_YEARS} years")
    axes[0].set_title("Substation age distribution")
    axes[0].set_xlabel("Asset age (years)")
    axes[0].set_ylabel("Substations")
    axes[0].legend()

    frame = age_by_region.sort_values("Mean Age (years)")
    axes[1].barh(frame.index, frame["Mean Age (years)"], color="#1f77b4",
                 edgecolor="black", linewidth=0.4)
    axes[1].set_title("Mean asset age by region")
    axes[1].set_xlabel("Years")
    fig.savefig(FIGURES / filename, dpi=150)
    plt.close(fig)


def figure_concentration(shares, filename):
    ordered = shares.sort_values(ascending=False).values
    cumulative = np.cumsum(ordered)
    fraction = np.arange(1, len(ordered) + 1) / len(ordered)
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.plot(100 * fraction, 100 * cumulative, color="#1f77b4", linewidth=2,
            label="Observed capacity concentration")
    ax.plot([0, 100], [0, 100], color="#7f7f7f", linestyle="--",
            label="Perfectly even distribution")
    ax.set_title("Cumulative share of national capacity")
    ax.set_xlabel("Share of substations, largest first (%)")
    ax.set_ylabel("Cumulative share of capacity (%)")
    ax.legend()
    fig.savefig(FIGURES / filename, dpi=150)
    plt.close(fig)


def figure_bi_dashboard(footprint, reliability, opportunities, bands, filename):
    fig, axes = plt.subplots(2, 2, figsize=(15, 11))

    utilities = footprint.sort_values("Total Length (km)")
    axes[0][0].barh(utilities["Alias"], utilities["Total Length (km)"],
                    color="#1f77b4", edgecolor="black", linewidth=0.4)
    axes[0][0].set_title("Network length operated by utility")
    axes[0][0].set_xlabel("Total line length (km)")

    risk = reliability.head(10).iloc[::-1]
    axes[0][1].barh(risk.index, risk["Reliability Risk Score"], color="#d62728",
                    edgecolor="black", linewidth=0.4)
    axes[0][1].set_title("Regional reliability risk score")
    axes[0][1].set_xlabel("Composite score (0 to 1)")

    opportunity = opportunities.head(10).iloc[::-1]
    axes[1][0].barh(opportunity.index, opportunity["Opportunity Score"],
                    color="#2ca02c", edgecolor="black", linewidth=0.4)
    axes[1][0].set_title("Regional growth opportunity score")
    axes[1][0].set_xlabel("Composite score (0 to 1)")

    axes[1][1].bar(bands.index, bands["Substations"], color="#ff7f0e",
                   edgecolor="black", linewidth=0.4)
    axes[1][1].set_title("Substations by capacity utilisation band")
    axes[1][1].set_ylabel("Substations")
    plt.setp(axes[1][1].get_xticklabels(), rotation=20, ha="right")

    fig.suptitle("GridCare business intelligence dashboard", fontsize=15)
    fig.savefig(FIGURES / filename, dpi=150)
    plt.close(fig)


def figure_loss_proxy(footprint, reliability, filename):
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    utilities = footprint.sort_values("Total Loss Index")
    axes[0].barh(utilities["Alias"], utilities["Total Loss Index"], color="#9467bd",
                 edgecolor="black", linewidth=0.4)
    axes[0].set_title("Technical loss proxy by utility")
    axes[0].set_xlabel("Loss index (length scaled by inverse voltage squared)")

    regions = reliability.sort_values("Loss Index")
    axes[1].barh(regions.index, regions["Loss Index"], color="#e377c2",
                 edgecolor="black", linewidth=0.4)
    axes[1].set_title("Technical loss proxy by region")
    axes[1].set_xlabel("Loss index")
    fig.savefig(FIGURES / filename, dpi=150)
    plt.close(fig)


def write_reports(footprint, idle, by_region, by_voltage, upgrade, bands, concentration,
                  age_bands, age_by_region, age_by_type, oldest, reliability,
                  opportunities, recommendations):
    md = ["# Task 2.3 Business Intelligence and Reliability Report", ""]
    md.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    md.append("")
    md.append("Every indicator below is a proxy computed from a synthetic asset register. "
              "None of them measure real load, real losses or real fault rates.")
    md.append("")
    md.append("## 1. Utility footprint")
    md.append("")
    md.append(to_md(footprint[["Alias", "Type", "Country", "Lines", "Substations Touched",
                               "Regions Served", "Total Length (km)",
                               "Inter-Regional Lines", "Maintenance Share %"]]))
    md.append("")
    if len(idle):
        md.append(f"{len(idle)} registered utilities operate no lines in this dataset: "
                  f"{', '.join(idle['Alias'].tolist())}. Generation-only and inactive "
                  f"companies appear in the register without owning transmission assets.")
        md.append("")
    md.append("### Lines by utility and source region")
    md.append("")
    md.append(to_md(by_region, index=True, index_label="Utility"))
    md.append("")
    md.append("### Lines by utility and voltage tier")
    md.append("")
    md.append(to_md(by_voltage, index=True, index_label="Utility"))
    md.append("")
    md.append("## 2. Capacity utilisation")
    md.append("")
    md.append("Capacity utilisation is the total rated capacity of the lines meeting a "
              "substation divided by the substation's own rating. It is a provisioning "
              "proxy, not a measured loading.")
    md.append("")
    md.append("Read the result below as a data-quality finding first. The generator draws "
              "substation capacity and line capacity from independent ranges, so line "
              "ratings routinely exceed the ratings of the substations they terminate on. "
              "The ratio is therefore evidence that the two rating fields in the register "
              "are inconsistent, not evidence that the network is overloaded. In a real "
              "register the same test would be a useful screen; here it mainly shows that "
              "the synthetic data has no coherent rating model.")
    md.append("")
    md.append(to_md(bands, index=True, index_label="Utilisation band"))
    md.append("")
    md.append("### Upgrade candidates")
    md.append("")
    md.append(to_md(upgrade))
    md.append("")
    md.append("### Capacity concentration")
    md.append("")
    md.append("| Measure | Value |")
    md.append("| --- | --- |")
    for key, value in concentration.items():
        md.append(f"| {key} | {value} |")
    md.append("")
    md.append("The Herfindahl-Hirschman Index treats each substation's share of national "
              "capacity as a market share. A higher value means capacity sits in fewer "
              "sites, which raises the consequence of losing any one of them.")
    md.append("")
    md.append("## 3. Asset age profile")
    md.append("")
    md.append(to_md(age_bands, index=True, index_label="Age band"))
    md.append("")
    md.append(to_md(age_by_region, index=True, index_label="Region"))
    md.append("")
    md.append(to_md(age_by_type, index=True, index_label="Substation type"))
    md.append("")
    md.append("### Oldest assets")
    md.append("")
    md.append(to_md(oldest))
    md.append("")
    md.append("## 4. Reliability proxy analysis")
    md.append("")
    md.append(f"The regional risk score combines maintenance share "
              f"({RISK_WEIGHTS['maintenance_share']:.0%}), mean asset age "
              f"({RISK_WEIGHTS['mean_age']:.0%}), capacity concentration "
              f"({RISK_WEIGHTS['capacity_concentration']:.0%}) and bridge dependency "
              f"({RISK_WEIGHTS['bridge_dependency']:.0%}). Bridge dependency comes from the "
              f"Task 2.1 network analysis, which is what connects the reliability view to "
              f"the topology.")
    md.append("")
    md.append("Lines are attributed to the region of their source substation, so an "
              "inter-regional line is counted once rather than in both regions.")
    md.append("")
    md.append(to_md(reliability[["Substations", "Lines", "Maintenance Share %",
                                 "Mean Age (years)", "Capacity Concentration",
                                 "Bridge Dependency %", "Reliability Risk Score"]],
                    index=True, index_label="Region"))
    md.append("")
    md.append("## 5. Growth opportunities")
    md.append("")
    md.append(to_md(opportunities, index=True, index_label="Region"))
    md.append("")
    md.append("A high opportunity score means thin coverage relative to the rest of the "
              "network. It is a screening indicator only: without demand, population and "
              "land-area data it cannot show that the coverage is inadequate.")
    md.append("")
    md.append("## 6. Outputs")
    md.append("")
    md.append("- `reports/bi_tables/*.csv`")
    md.append("- `figures/40_bi_dashboard.png`, `41_capacity_utilisation.png`, "
              "`42_asset_age_profile.png`, `43_capacity_concentration.png`, "
              "`44_loss_proxy.png`")
    md.append("- `reports/strategic_recommendations.md`")
    md.append("")
    (REPORTS / "reliability_report.md").write_text("\n".join(md), encoding="utf-8")

    lines = ["# Strategic Recommendations", ""]
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("These recommendations follow from the Week 2 analysis of a synthetic "
                 "dataset. They are framed as investigations to open, not decisions to "
                 "take. No conclusion here should be applied to real infrastructure "
                 "without operational data.")
    lines.append("")
    for priority in ["High", "Medium", "Low"]:
        subset = recommendations[recommendations["Priority"] == priority]
        if not len(subset):
            continue
        lines.append(f"## {priority} priority")
        lines.append("")
        for index, row in enumerate(subset.to_dict("records"), start=1):
            lines.append(f"### {index}. {row['Theme']}: {row['Area']}")
            lines.append("")
            lines.append(f"- Finding: {row['Finding']}")
            lines.append(f"- Action: {row['Recommended action']}")
            lines.append("")
    lines.append("## Method and limits")
    lines.append("")
    lines.append("- Criticality and bridge dependency come from a topological model, not a "
                 "power-flow study.")
    lines.append("- Capacity utilisation compares register ratings, not measured flows. In "
                 "this synthetic dataset the two rating fields are drawn independently, so "
                 "the ratio reads as a data-consistency check rather than a loading "
                 "measurement.")
    lines.append("- The loss index scales line length by the inverse square of voltage. It "
                 "ranks corridors sensibly but is not a loss figure in megawatts.")
    lines.append("- Asset age is a fault-risk proxy. Condition, maintenance history and "
                 "duty would all change the picture.")
    lines.append("")
    (REPORTS / "strategic_recommendations.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    for directory in (TABLES, FIGURES, REPORTS):
        directory.mkdir(parents=True, exist_ok=True)

    utilities, substations, lines = load_clean()
    ranking = load_optional(NETWORK_TABLES / "criticality_ranking.csv")
    bridges = load_optional(NETWORK_TABLES / "bridge_lines.csv")
    density = load_optional(GEO_TABLES / "regional_density.csv")

    annotated_lines = annotate_lines(substations, lines)
    annotated_substations = annotate_substations(substations, annotated_lines)

    footprint, idle, by_region, by_voltage = utility_footprint(
        utilities, annotated_lines)
    upgrade, bands, concentration, shares = capacity_analysis(annotated_substations, ranking)
    age_bands, age_by_region, age_by_type, oldest = age_profile(annotated_substations)
    reliability = reliability_analysis(annotated_lines, annotated_substations, bridges)
    opportunities = growth_opportunities(reliability, density)
    recommendations = strategic_recommendations(
        reliability, opportunities, upgrade, oldest, footprint, concentration, ranking,
        bridges)

    annotated_lines.to_csv(TABLES / "lines_with_indicators.csv", index=False)
    annotated_substations.to_csv(TABLES / "substations_with_indicators.csv", index=False)
    footprint.to_csv(TABLES / "utility_footprint.csv", index=False)
    by_region.to_csv(TABLES / "utility_lines_by_region.csv")
    by_voltage.to_csv(TABLES / "utility_lines_by_voltage.csv")
    upgrade.to_csv(TABLES / "upgrade_candidates.csv", index=False)
    bands.to_csv(TABLES / "utilisation_bands.csv")
    pd.DataFrame(list(concentration.items()), columns=["Measure", "Value"]).to_csv(
        TABLES / "capacity_concentration.csv", index=False)
    age_bands.to_csv(TABLES / "age_bands.csv")
    age_by_region.to_csv(TABLES / "age_by_region.csv")
    age_by_type.to_csv(TABLES / "age_by_type.csv")
    oldest.to_csv(TABLES / "oldest_assets.csv", index=False)
    reliability.to_csv(TABLES / "regional_reliability.csv")
    opportunities.to_csv(TABLES / "growth_opportunities.csv")
    recommendations.to_csv(TABLES / "strategic_recommendations.csv", index=False)

    figure_bi_dashboard(footprint, reliability, opportunities, bands, "40_bi_dashboard.png")
    figure_capacity_utilisation(annotated_substations, "41_capacity_utilisation.png")
    figure_age_profile(annotated_substations, age_by_region, "42_asset_age_profile.png")
    figure_concentration(shares, "43_capacity_concentration.png")
    figure_loss_proxy(footprint, reliability, "44_loss_proxy.png")

    write_reports(footprint, idle, by_region, by_voltage, upgrade, bands, concentration,
                  age_bands, age_by_region, age_by_type, oldest, reliability,
                  opportunities, recommendations)

    if ranking is None:
        print("Note: run task2_1_network_analysis.py first to include bridge dependency "
              "and criticality in this report.")
    print("Utility footprint")
    print(footprint[["Alias", "Lines", "Total Length (km)", "Maintenance Share %"]]
          .to_string(index=False))
    print("\nCapacity concentration")
    for key, value in concentration.items():
        print(f"  {key}: {value}")
    print("\nRegional reliability risk")
    print(reliability[["Substations", "Maintenance Share %", "Mean Age (years)",
                       "Bridge Dependency %", "Reliability Risk Score"]].to_string())
    print("\nGrowth opportunities")
    print(opportunities.head(5).to_string())
    print(f"\nRecommendations generated: {len(recommendations)}")
    print(f"Tables: {TABLES}")
    print(f"Reports: {REPORTS / 'reliability_report.md'}, "
          f"{REPORTS / 'strategic_recommendations.md'}")
    return footprint, reliability, opportunities, recommendations


if __name__ == "__main__":
    main()
