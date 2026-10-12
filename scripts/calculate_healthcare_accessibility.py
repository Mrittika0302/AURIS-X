
import json
import math
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd


# ============================================================
# AURIS-X
# Healthcare accessibility analysis
# Coimbatore, Tamil Nadu, India
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

POPULATION_CSV = (
    ROOT / "data" / "silver" / "population_road_matches.csv"
)

FACILITIES_CSV = (
    ROOT / "data" / "silver"
    / "healthcare_network_matches_20261011_122708.csv"
)

DRIVING_GRAPH = (
    ROOT / "data" / "raw"
    / "roads_osm_20261011_115925.graphml"
)

WALKING_GRAPH = (
    ROOT / "data" / "raw"
    / "roads_walking_osm_20261011_122708.graphml"
)

OUTPUT_CSV = (
    ROOT / "data" / "gold"
    / "healthcare_accessibility_by_population_cell.csv"
)

OUTPUT_JSON = (
    ROOT / "reports"
    / "healthcare_accessibility_summary.json"
)

THRESHOLDS_METRES = [500, 1000, 2000, 5000, 10000]


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def find_column(df, candidates, description, required=True):
    """Find a column using case-insensitive candidate names."""
    columns = {
        str(column).strip().lower(): column
        for column in df.columns
    }

    for candidate in candidates:
        key = candidate.strip().lower()
        if key in columns:
            return columns[key]

    if not required:
        return None

    raise ValueError(
        f"Could not identify {description} column.\n"
        f"Tried: {candidates}\n"
        f"Available columns: {list(df.columns)}"
    )


def normalize_id(value):
    """Normalize IDs while preserving missing values."""
    if pd.isna(value):
        return None
    return str(value).strip()


def load_graph(path, label):
    """Load GraphML and convert all edge lengths to numeric metres."""
    if not path.exists():
        raise FileNotFoundError(f"{label} graph not found: {path}")

    print(f"\nLoading {label} graph...")
    graph = nx.read_graphml(path)

    # Make node IDs consistent with CSV IDs.
    graph = nx.relabel_nodes(
        graph,
        {node: str(node) for node in graph.nodes},
        copy=True,
    )

    invalid = []
    edge_lengths = []

    if graph.is_multigraph():
        for u, v, key, attrs in graph.edges(keys=True, data=True):
            try:
                length = float(attrs["length"])

                if not math.isfinite(length) or length <= 0:
                    raise ValueError("length must be finite and positive")

                attrs["length"] = length
                edge_lengths.append(length)

            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                invalid.append(f"{u}->{v} edge {key}: {exc}")
    else:
        for u, v, attrs in graph.edges(data=True):
            try:
                length = float(attrs["length"])

                if not math.isfinite(length) or length <= 0:
                    raise ValueError("length must be finite and positive")

                attrs["length"] = length
                edge_lengths.append(length)

            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                invalid.append(f"{u}->{v}: {exc}")

    if invalid:
        raise ValueError(
            f"{label} graph has {len(invalid)} invalid edge lengths. "
            f"Examples: {'; '.join(invalid[:5])}"
        )

    if not edge_lengths:
        raise ValueError(f"{label} graph contains no valid edge lengths.")

    print(f"Nodes: {graph.number_of_nodes():,}")
    print(f"Edges: {graph.number_of_edges():,}")
    print(f"Minimum edge length: {min(edge_lengths):.2f}")
    print(f"Median edge length: {np.median(edge_lengths):.2f}")
    print(f"Maximum edge length: {max(edge_lengths):.2f}")

    return graph


# ------------------------------------------------------------
# Load population and facility match tables
# ------------------------------------------------------------

def load_input_data():
    for path in [POPULATION_CSV, FACILITIES_CSV]:
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {path}")

    population = pd.read_csv(POPULATION_CSV)
    facilities = pd.read_csv(FACILITIES_CSV)

    print(f"\nPopulation match rows: {len(population):,}")
    print(f"Healthcare facility records: {len(facilities):,}")

    print("\nPopulation columns:")
    print(list(population.columns))

    print("\nHealthcare facility columns:")
    print(list(facilities.columns))

    # Confirmed names from your population CSV are listed first.
    pop_id_col = find_column(
        population,
        ["population_cell_id", "cell_id", "pixel_id"],
        "population cell ID",
    )

    pop_drive_col = find_column(
        population,
        [
            "drive_nearest_node_id",
            "driving_node",
            "drive_node",
            "driving_node_id",
            "nearest_driving_node",
            "drive_node_id",
            "driving_osmid",
        ],
        "population driving node",
    )

    pop_walk_col = find_column(
        population,
        [
            "walk_nearest_node_id",
            "walking_node",
            "walk_node",
            "walking_node_id",
            "nearest_walking_node",
            "walk_node_id",
            "walking_osmid",
        ],
        "population walking node",
    )

    facility_id_col = find_column(
        facilities,
        [
            "osm_id",
            "facility_osm_id",
            "osmid",
            "facility_id",
            "id",
        ],
        "healthcare facility ID",
    )

    # Accept several common naming conventions for snapped nodes.
    facility_drive_col = find_column(
        facilities,
        [
            "drive_nearest_node_id",
            "driving_nearest_node_id",
            "drive_node_id",
            "driving_node_id",
            "driving_node",
            "drive_node",
            "nearest_driving_node",
            "driving_osmid",
            "nearest_drive_node_id",
        ],
        "healthcare facility driving node",
    )

    facility_walk_col = find_column(
        facilities,
        [
            "walk_nearest_node_id",
            "walking_nearest_node_id",
            "walk_node_id",
            "walking_node_id",
            "walking_node",
            "walk_node",
            "nearest_walking_node",
            "walking_osmid",
            "nearest_walk_node_id",
        ],
        "healthcare facility walking node",
    )

    name_col = find_column(
        facilities,
        ["name", "facility_name", "healthcare_name", "osm_name"],
        "facility name",
        required=False,
    )

    category_col = find_column(
        facilities,
        [
            "category",
            "healthcare",
            "amenity",
            "facility_type",
            "type",
        ],
        "facility category",
        required=False,
    )

    population = population.copy()
    facilities = facilities.copy()

    population["_cell_id"] = population[pop_id_col].map(normalize_id)
    population["_drive_node"] = population[pop_drive_col].map(normalize_id)
    population["_walk_node"] = population[pop_walk_col].map(normalize_id)

    facilities["_facility_id"] = facilities[facility_id_col].map(normalize_id)
    facilities["_drive_node"] = facilities[facility_drive_col].map(normalize_id)
    facilities["_walk_node"] = facilities[facility_walk_col].map(normalize_id)

    if name_col:
        facilities["_facility_name"] = (
            facilities[name_col].fillna("").astype(str)
        )
    else:
        facilities["_facility_name"] = ""

    if category_col:
        facilities["_facility_category"] = (
            facilities[category_col].fillna("").astype(str)
        )
    else:
        facilities["_facility_category"] = ""

    if population["_cell_id"].isna().any():
        raise ValueError("Population CSV contains missing cell IDs.")

    if population["_cell_id"].duplicated().any():
        count = int(population["_cell_id"].duplicated().sum())
        raise ValueError(
            f"Population CSV contains {count} duplicate cell IDs."
        )

    return population, facilities


# ------------------------------------------------------------
# Facility source nodes
# ------------------------------------------------------------

def get_facility_sources(graph, facilities, mode):
    node_column = "_drive_node" if mode == "driving" else "_walk_node"
    graph_nodes = set(graph.nodes)

    sources = {}
    missing = 0

    for _, row in facilities.iterrows():
        node = row[node_column]

        if node is None or pd.isna(node) or node not in graph_nodes:
            missing += 1
            continue

        if node not in sources:
            sources[node] = {
                "facility_id": row["_facility_id"] or "",
                "facility_name": row["_facility_name"],
                "facility_category": row["_facility_category"],
            }

    print(f"\n{mode.title()} network")
    print(f"Facility records: {len(facilities):,}")
    print(f"Unique valid facility source nodes: {len(sources):,}")
    print(f"Records with missing or invalid source nodes: {missing:,}")

    if not sources:
        raise ValueError(
            f"No valid healthcare facility nodes found for {mode}."
        )

    return sources


# ------------------------------------------------------------
# Nearest facility network distance
# ------------------------------------------------------------

def calculate_accessibility(graph, population_nodes, sources, mode):
    """
    Calculate shortest network distance from each population node
    to its nearest reachable facility.

    Reverse-graph multi-source Dijkstra allows search from facility
    nodes while measuring population-to-facility distance in the
    original directed graph.
    """
    graph_nodes = set(graph.nodes)

    nodes = [
        normalize_id(node)
        for node in population_nodes
    ]

    valid_sources = {
        node: metadata
        for node, metadata in sources.items()
        if node in graph_nodes
    }

    valid_population_count = sum(
        node is not None and node in graph_nodes
        for node in nodes
    )

    missing_population_count = len(nodes) - valid_population_count

    print(f"\n{mode.title()} population nodes: {len(nodes):,}")
    print(f"Population nodes present in graph: {valid_population_count:,}")
    print(f"Population nodes missing from graph: {missing_population_count:,}")
    print("Running multi-source Dijkstra; this may take a few minutes...")

    if not valid_sources:
        raise ValueError(f"No valid facility sources for {mode}.")

    reverse_graph = graph.reverse(copy=False)

    distances, paths = nx.multi_source_dijkstra(
        reverse_graph,
        sources=list(valid_sources.keys()),
        weight="length",
    )

    print(f"Nodes reached by Dijkstra: {len(distances):,}")

    results = []

    for node in nodes:
        distance = distances.get(node) if node is not None else None

        if distance is None:
            results.append({
                f"{mode}_distance_m": np.nan,
                f"{mode}_facility_id": "",
                f"{mode}_facility_name": "",
                f"{mode}_facility_category": "",
                f"{mode}_reachable": False,
            })
            continue

        path = paths.get(node, [])
        source_node = path[0] if path else None
        metadata = valid_sources.get(source_node, {})

        results.append({
            f"{mode}_distance_m": float(distance),
            f"{mode}_facility_id": metadata.get("facility_id", ""),
            f"{mode}_facility_name": metadata.get("facility_name", ""),
            f"{mode}_facility_category": metadata.get(
                "facility_category", ""
            ),
            f"{mode}_reachable": True,
        })

    return results


# ------------------------------------------------------------
# Summary statistics
# ------------------------------------------------------------

def summarize_distances(df, mode):
    distance_col = f"{mode}_distance_m"
    distances = pd.to_numeric(df[distance_col], errors="coerce")
    reachable = distances.notna()
    total = len(df)

    summary = {
        "mode": mode,
        "population_cell_count": int(total),
        "reachable_cell_count": int(reachable.sum()),
        "unreachable_or_unmatched_cell_count": int((~reachable).sum()),
        "reachable_percent": round(
            float(reachable.sum() / total * 100), 2
        ) if total else 0.0,
        "distance_statistics_m": {},
        "cells_within_network_distance_thresholds": {},
    }

    if reachable.any():
        valid = distances[reachable]

        summary["distance_statistics_m"] = {
            "minimum": round(float(valid.min()), 2),
            "median": round(float(valid.median()), 2),
            "mean": round(float(valid.mean()), 2),
            "p90": round(float(valid.quantile(0.90)), 2),
            "p95": round(float(valid.quantile(0.95)), 2),
            "maximum": round(float(valid.max()), 2),
        }

    for threshold in THRESHOLDS_METRES:
        count = int((distances.notna() & (distances <= threshold)).sum())

        summary["cells_within_network_distance_thresholds"][
            f"{threshold}_m"
        ] = {
            "cell_count": count,
            "percent_of_all_cells": round(
                count / total * 100, 2
            ) if total else 0.0,
        }

    return summary


# ------------------------------------------------------------
# Main workflow
# ------------------------------------------------------------

def main():
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    population, facilities = load_input_data()

    driving_graph = load_graph(DRIVING_GRAPH, "Driving")
    walking_graph = load_graph(WALKING_GRAPH, "Walking")

    driving_sources = get_facility_sources(
        driving_graph, facilities, "driving"
    )

    walking_sources = get_facility_sources(
        walking_graph, facilities, "walking"
    )

    driving_results = calculate_accessibility(
        driving_graph,
        population["_drive_node"].tolist(),
        driving_sources,
        "driving",
    )

    walking_results = calculate_accessibility(
        walking_graph,
        population["_walk_node"].tolist(),
        walking_sources,
        "walking",
    )

    output = population.drop(
        columns=["_cell_id", "_drive_node", "_walk_node"],
        errors="ignore",
    ).copy()

    output = pd.concat(
        [
            output.reset_index(drop=True),
            pd.DataFrame(driving_results),
            pd.DataFrame(walking_results),
        ],
        axis=1,
    )

    output.to_csv(
        OUTPUT_CSV,
        index=False,
        encoding="utf-8-sig",
    )

    summary = {
        "project": "AURIS-X",
        "analysis": "Nearest mapped healthcare facility accessibility",
        "study_area": "Coimbatore, Tamil Nadu, India",
        "distance_unit": "metres",
        "thresholds_metres": THRESHOLDS_METRES,
        "input_files": {
            "population_matches": str(POPULATION_CSV.relative_to(ROOT)),
            "healthcare_facilities": str(FACILITIES_CSV.relative_to(ROOT)),
            "driving_graph": str(DRIVING_GRAPH.relative_to(ROOT)),
            "walking_graph": str(WALKING_GRAPH.relative_to(ROOT)),
        },
        "output_csv": str(OUTPUT_CSV.relative_to(ROOT)),
        "method_notes": [
            "GraphML edge lengths are converted to finite positive numeric values.",
            "Distances are shortest path lengths on the mapped road networks.",
            "Unreachable or unmatched population nodes receive missing distances.",
            "Facilities sharing a snapped node are represented by the first record at that node.",
            "The output is network distance, not travel time.",
            "Facility operational status, capacity, and quality have not been verified.",
            "Population raster values are retained as provided and are not assumed to be headcounts.",
            "Results require further validation against real routes and facilities.",
        ],
        "driving": summarize_distances(output, "driving"),
        "walking": summarize_distances(output, "walking"),
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2, ensure_ascii=False)

    print("\n" + "=" * 65)
    print("AURIS-X HEALTHCARE ACCESSIBILITY ANALYSIS COMPLETE")
    print("=" * 65)
    print(f"Population cells processed: {len(output):,}")
    print(f"Healthcare records: {len(facilities):,}")
    print(f"\nCSV output: {OUTPUT_CSV}")
    print(f"JSON summary: {OUTPUT_JSON}")

    for mode in ["driving", "walking"]:
        item = summary[mode]
        stats = item["distance_statistics_m"]

        print(f"\n{mode.title()}:")
        print(f"  Reachable cells: {item['reachable_cell_count']:,}")
        print(
            "  Unreachable/unmatched cells: "
            f"{item['unreachable_or_unmatched_cell_count']:,}"
        )

        if stats:
            print(f"  Median distance: {stats['median']:,.2f} m")
            print(f"  Mean distance: {stats['mean']:,.2f} m")
            print(f"  P90 distance: {stats['p90']:,.2f} m")

    print("\nNote: results are preliminary network-distance estimates.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("\nERROR: Healthcare accessibility calculation failed.")
        print(f"{type(exc).__name__}: {exc}")
        raise
