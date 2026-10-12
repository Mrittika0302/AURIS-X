
import math
from pathlib import Path

import networkx as nx
import pandas as pd


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
ACCESSIBILITY_CSV = (
    ROOT / "data" / "gold"
    / "healthcare_accessibility_by_population_cell.csv"
)

SAMPLE_SIZE = 30
SEED = 42
TOLERANCE_METRES = 0.01


def normalize_id(value):
    """Normalize graph-node identifiers without converting to integers."""
    if pd.isna(value):
        return None
    value = str(value).strip()
    return value if value else None


def load_graph(path, label):
    """Load a directed road graph and normalize node IDs and edge lengths."""
    print(f"\nLoading {label} graph...")

    graph = nx.read_graphml(path)

    graph = nx.relabel_nodes(
        graph,
        {node: str(node) for node in graph.nodes},
        copy=True,
    )

    invalid_lengths = 0

    for _, _, _, attrs in graph.edges(keys=True, data=True):
        try:
            length = float(attrs["length"])
            if not math.isfinite(length) or length <= 0:
                raise ValueError("Edge length must be positive and finite")
            attrs["length"] = length
        except (KeyError, TypeError, ValueError):
            invalid_lengths += 1

    if invalid_lengths:
        raise ValueError(
            f"{label} graph has {invalid_lengths} edges with "
            "missing or invalid lengths. Validation stopped."
        )

    print(
        f"{label}: {graph.number_of_nodes():,} nodes, "
        f"{graph.number_of_edges():,} edges"
    )

    return graph


def independent_distances(graph, population_nodes, facility_nodes):
    """
    Independently compute each sampled population node's shortest
    directed path to any valid facility node.

    Paths are measured in the original graph, from population to facility.
    """
    results = []

    valid_facilities = {
        node for node in facility_nodes
        if node is not None and node in graph
    }

    if not valid_facilities:
        raise ValueError("No facility snap nodes exist in this graph.")

    for pop_node in population_nodes:
        if pop_node is None or pop_node not in graph:
            results.append(math.nan)
            continue

        # Correct direction: population node -> other nodes in original graph.
        distances = nx.single_source_dijkstra_path_length(
            graph,
            source=pop_node,
            weight="length",
        )

        reachable_distances = [
            distances[node]
            for node in valid_facilities
            if node in distances
        ]

        results.append(
            float(min(reachable_distances))
            if reachable_distances
            else math.nan
        )

    return results


def compare_mode(
    label,
    graph,
    sample,
    population_node_col,
    facility_node_col,
    result_distance_col,
    facilities,
):
    print(f"\n=== {label.upper()} VALIDATION ===")

    population_nodes = sample[population_node_col].map(
        normalize_id
    ).tolist()

    facility_nodes = facilities[facility_node_col].map(
        normalize_id
    ).dropna().unique().tolist()

    missing_population_nodes = sum(
        node is None or node not in graph
        for node in population_nodes
    )

    missing_facility_nodes = sum(
        node is None or node not in graph
        for node in facility_nodes
    )

    print(
        "Sample population nodes missing from graph:",
        missing_population_nodes,
    )
    print(
        "Unique facility snap nodes missing from graph:",
        missing_facility_nodes,
    )

    independent = independent_distances(
        graph,
        population_nodes,
        facility_nodes,
    )

    recorded = pd.to_numeric(
        sample[result_distance_col],
        errors="coerce",
    ).tolist()

    rows = []

    for cell_id, expected, existing in zip(
        sample["population_cell_id"],
        independent,
        recorded,
    ):
        if pd.isna(expected) and pd.isna(existing):
            status = "BOTH_UNREACHABLE"
            difference = math.nan

        elif pd.isna(expected) != pd.isna(existing):
            status = "REACHABILITY_MISMATCH"
            difference = math.nan

        else:
            difference = abs(float(expected) - float(existing))
            status = (
                "MATCH"
                if difference <= TOLERANCE_METRES
                else "DISTANCE_MISMATCH"
            )

        rows.append({
            "population_cell_id": cell_id,
            "independent_distance_m": expected,
            "existing_distance_m": existing,
            "absolute_difference_m": difference,
            "status": status,
        })

    comparison = pd.DataFrame(rows)

    print("Sampled cells:", len(comparison))
    print("\nStatus counts:")
    print(
        comparison["status"]
        .value_counts(dropna=False)
        .to_string()
    )

    differences = pd.to_numeric(
        comparison["absolute_difference_m"],
        errors="coerce",
    ).dropna()

    if not differences.empty:
        print(
            "\nMedian absolute difference: "
            f"{differences.median():.6f} m"
        )
        print(
            "Maximum absolute difference: "
            f"{differences.max():.6f} m"
        )

    discrepancies = comparison[
        comparison["status"].isin([
            "REACHABILITY_MISMATCH",
            "DISTANCE_MISMATCH",
        ])
    ]

    if not discrepancies.empty:
        print("\nFirst discrepancies:")
        print(discrepancies.head(10).to_string(index=False))
    else:
        print("\nNo discrepancies found in this sample.")

    return comparison


def main():
    required_files = [
        POPULATION_CSV,
        FACILITIES_CSV,
        DRIVING_GRAPH,
        WALKING_GRAPH,
        ACCESSIBILITY_CSV,
    ]

    for path in required_files:
        if not path.exists():
            raise FileNotFoundError(
                f"Required input file not found: {path}"
            )

    print("Read-only healthcare accessibility validation")
    print(f"Sample size: {SAMPLE_SIZE}")
    print(f"Random seed: {SEED}")
    print(f"Distance tolerance: {TOLERANCE_METRES} metres")

    # Read identifiers as strings to avoid accidental type conversion.
    facilities = pd.read_csv(FACILITIES_CSV, dtype=str)
    access = pd.read_csv(ACCESSIBILITY_CSV, dtype=str)

    required_facility_columns = [
        "drive_nearest_node_id",
        "walk_nearest_node_id",
    ]

    for column in required_facility_columns:
        if column not in facilities.columns:
            raise ValueError(
                f"Facility file is missing column: {column}"
            )

    required_access_columns = [
        "population_cell_id",
        "drive_nearest_node_id",
        "walk_nearest_node_id",
        "driving_distance_m",
        "walking_distance_m",
    ]

    for column in required_access_columns:
        if column not in access.columns:
            raise ValueError(
                f"Accessibility file is missing column: {column}"
            )

    if access["population_cell_id"].duplicated().any():
        raise ValueError(
            "Accessibility file contains duplicate population_cell_id "
            "values. Validation stopped to avoid ambiguous comparisons."
        )

    sample = access.sample(
        n=min(SAMPLE_SIZE, len(access)),
        random_state=SEED,
    ).reset_index(drop=True)

    driving_graph = load_graph(DRIVING_GRAPH, "Driving")
    walking_graph = load_graph(WALKING_GRAPH, "Walking")

    # Validate driving distances against driving facility snap nodes.
    compare_mode(
        label="Driving",
        graph=driving_graph,
        sample=sample,
        population_node_col="drive_nearest_node_id",
        facility_node_col="drive_nearest_node_id",
        result_distance_col="driving_distance_m",
        facilities=facilities,
    )

    # Validate walking distances against walking facility snap nodes.
    compare_mode(
        label="Walking",
        graph=walking_graph,
        sample=sample,
        population_node_col="walk_nearest_node_id",
        facility_node_col="walk_nearest_node_id",
        result_distance_col="walking_distance_m",
        facilities=facilities,
    )

    print("\n=== DRIVING/WALKING DISTANCE COMPARISON ===")

    driving_values = pd.to_numeric(
        sample["driving_distance_m"],
        errors="coerce",
    )
    walking_values = pd.to_numeric(
        sample["walking_distance_m"],
        errors="coerce",
    )

    both_valid = driving_values.notna() & walking_values.notna()
    exact_matches = (
        driving_values[both_valid] == walking_values[both_valid]
    )

    print(
        "Sampled cells with exactly equal recorded distances:",
        int(exact_matches.sum()),
        "of",
        int(both_valid.sum()),
    )

    differences = pd.DataFrame({
        "population_cell_id": sample["population_cell_id"],
        "driving_m": driving_values,
        "walking_m": walking_values,
    })

    differences["absolute_difference_m"] = (
        differences["driving_m"] - differences["walking_m"]
    ).abs()

    print("\nLargest recorded mode differences:")
    print(
        differences.sort_values(
            "absolute_difference_m",
            ascending=False,
        ).head(10).to_string(index=False)
    )

    print("\nDONE — no files changed.")
    print(
        "This checks shortest distances to any valid facility snap node "
        "in each graph. It does not validate the assigned facility "
        "metadata or establish real-world route accuracy."
    )


if __name__ == "__main__":
    main()
