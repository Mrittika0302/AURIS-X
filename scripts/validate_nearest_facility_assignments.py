
from pathlib import Path
import pandas as pd
import networkx as nx
import osmnx as ox

ROOT = Path(__file__).resolve().parents[1]

ACCESS_FILE = ROOT / "data" / "gold" / "healthcare_accessibility_by_population_cell.csv"
POPULATION_FILE = ROOT / "data" / "silver" / "population_road_matches.csv"
FACILITY_FILE = ROOT / "data" / "silver" / "healthcare_network_matches_20261011_122708.csv"
DRIVE_GRAPH_FILE = ROOT / "data" / "raw" / "roads_osm_20261011_115925.graphml"
WALK_GRAPH_FILE = ROOT / "data" / "raw" / "roads_walking_osm_20261011_122708.graphml"

SAMPLE_SIZE = 30
RANDOM_SEED = 42
DISTANCE_TOLERANCE_M = 1.0


def norm(value):
    if pd.isna(value):
        return None
    return str(value).strip().removesuffix(".0")


def load_graph(path):
    graph = ox.load_graphml(path)
    graph = nx.relabel_nodes(
        graph,
        {node: str(node) for node in graph.nodes},
        copy=True,
    )

    for _, _, _, data in graph.edges(keys=True, data=True):
        data["length"] = float(data["length"])
        if data["length"] <= 0:
            raise ValueError(f"Invalid edge length in {path.name}")

    return graph


def main():
    print("AURIS-X Nearest-Facility Validation - Corrected")
    print("Read-only: existing outputs will not be changed.")

    for path in (
        ACCESS_FILE,
        POPULATION_FILE,
        FACILITY_FILE,
        DRIVE_GRAPH_FILE,
        WALK_GRAPH_FILE,
    ):
        if not path.exists():
            raise FileNotFoundError(f"Missing file: {path}")

    access = pd.read_csv(ACCESS_FILE)
    population = pd.read_csv(POPULATION_FILE)
    facilities = pd.read_csv(
        FACILITY_FILE,
        dtype={"osm_id": "string"},
    )

    access["population_cell_id"] = access["population_cell_id"].astype(str)
    population["population_cell_id"] = population["population_cell_id"].astype(str)

    population = population[
        [
            "population_cell_id",
            "drive_nearest_node_id",
            "walk_nearest_node_id",
        ]
    ].rename(
        columns={
            "drive_nearest_node_id": "population_drive_node",
            "walk_nearest_node_id": "population_walk_node",
        }
    )

    for col in ("population_drive_node", "population_walk_node"):
        population[col] = population[col].map(norm)

    facilities["osm_id_norm"] = facilities["osm_id"].map(norm)

    for col in ("drive_nearest_node_id", "walk_nearest_node_id"):
        facilities[col] = facilities[col].map(norm)

    access["driving_facility_id_norm"] = access["driving_facility_id"].map(norm)
    access["walking_facility_id_norm"] = access["walking_facility_id"].map(norm)

    joined = access.merge(
        population,
        on="population_cell_id",
        how="left",
        validate="one_to_one",
    )

    print("\nLoading road graphs...")
    drive_graph = load_graph(DRIVE_GRAPH_FILE)
    walk_graph = load_graph(WALK_GRAPH_FILE)

    modes = [
        (
            "driving",
            drive_graph,
            "population_drive_node",
            "driving_distance_m",
            "driving_facility_id_norm",
            "drive_nearest_node_id",
        ),
        (
            "walking",
            walk_graph,
            "population_walk_node",
            "walking_distance_m",
            "walking_facility_id_norm",
            "walk_nearest_node_id",
        ),
    ]

    for (
        mode,
        graph,
        population_node_col,
        distance_col,
        assigned_id_col,
        facility_node_col,
    ) in modes:
        print("\n" + "=" * 65)
        print(f"{mode.upper()} VALIDATION")
        print("=" * 65)

        graph_nodes = set(graph.nodes)

        source = facilities.dropna(
            subset=["osm_id_norm", facility_node_col]
        ).copy()

        source = source[
            source[facility_node_col].isin(graph_nodes)
        ]

        facility_nodes = sorted(set(source[facility_node_col]))

        if not facility_nodes:
            print("ERROR: no valid facility nodes.")
            continue

        eligible = joined[
            joined[distance_col].notna()
            & joined[population_node_col].notna()
            & joined[population_node_col].isin(graph_nodes)
        ].copy()

        if eligible.empty:
            print("ERROR: no eligible population cells.")
            continue

        sample = eligible.sample(
            n=min(SAMPLE_SIZE, len(eligible)),
            random_state=RANDOM_SEED,
        )

        # Multi-source Dijkstra on the reversed graph gives the
        # minimum original-direction distance from each population
        # node to any reachable facility node.
        reverse_graph = graph.reverse(copy=False)

        min_distances, _ = nx.multi_source_dijkstra(
            reverse_graph,
            sources=facility_nodes,
            weight="length",
        )

        # Calculate shortest-path distances from each sampled
        # population node to its assigned facility node directly.
        results = []

        for _, row in sample.iterrows():
            pop_node = row[population_node_col]
            saved_distance = float(row[distance_col])
            assigned_id = row[assigned_id_col]

            calculated_min = min_distances.get(pop_node)

            assigned_records = source[
                source["osm_id_norm"] == assigned_id
            ]

            assigned_nodes = sorted(
                set(assigned_records[facility_node_col].dropna())
            )

            assigned_node_distances = []

            for node in assigned_nodes:
                try:
                    distance = nx.shortest_path_length(
                        graph,
                        source=pop_node,
                        target=node,
                        weight="length",
                    )
                    assigned_node_distances.append((node, distance))
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    continue

            assigned_distance = (
                min(distance for _, distance in assigned_node_distances)
                if assigned_node_distances
                else None
            )

            saved_matches_minimum = (
                calculated_min is not None
                and abs(saved_distance - calculated_min)
                <= DISTANCE_TOLERANCE_M
            )

            assigned_facility_is_nearest = (
                assigned_distance is not None
                and calculated_min is not None
                and abs(assigned_distance - calculated_min)
                <= DISTANCE_TOLERANCE_M
            )

            results.append(
                {
                    "population_cell_id": row["population_cell_id"],
                    "saved_distance_m": saved_distance,
                    "recalculated_minimum_m": calculated_min,
                    "saved_distance_matches_minimum": saved_matches_minimum,
                    "assigned_facility_id": assigned_id,
                    "assigned_facility_node_distance_m": assigned_distance,
                    "assigned_facility_is_nearest": assigned_facility_is_nearest,
                }
            )

        result = pd.DataFrame(results)

        print(f"Sample size: {len(result)}")
        print(
            "Saved distances match the minimum: "
            f"{int(result['saved_distance_matches_minimum'].sum())}/"
            f"{len(result)}"
        )
        print(
            "Assigned facility is a nearest facility: "
            f"{int(result['assigned_facility_is_nearest'].sum())}/"
            f"{len(result)}"
        )

        failures = result[
            ~result["assigned_facility_is_nearest"]
        ]

        if failures.empty:
            print("No assigned-facility distance discrepancies in this sample.")
        else:
            print("\nCases requiring investigation:")
            print(failures.to_string(index=False))

    print("\nValidation complete. No existing outputs were modified.")


if __name__ == "__main__":
    main()
