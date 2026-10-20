
from pathlib import Path

import numpy as np
import pandas as pd
import networkx as nx
import osmnx as ox

ROOT = Path(__file__).resolve().parents[1]

ACCESS = ROOT / "data/gold/healthcare_accessibility_by_population_cell.csv"
IMPACT = ROOT / "reports/candidate_impact_top10_20261012.csv"
DRIVE_GRAPH = ROOT / "data/raw/roads_osm_20261011_115925.graphml"
WALK_GRAPH = ROOT / "data/raw/roads_walking_osm_20261011_122708.graphml"

THRESHOLD_M = 5000.0
RANK_TO_CHECK = 8


def load_graph(path):
    graph = ox.load_graphml(path)
    graph = nx.relabel_nodes(graph, lambda n: str(n), copy=True)
    for _, _, _, data in graph.edges(keys=True, data=True):
        data["length"] = float(data["length"])
    return graph


def candidate_distances(graph, node, population_nodes):
    # Distances from population nodes to candidate in the original graph.
    reversed_graph = graph.reverse(copy=False)
    distances = nx.single_source_dijkstra_path_length(
        reversed_graph, node, weight="length"
    )
    return np.array(
        [distances.get(n, np.nan) for n in population_nodes],
        dtype=float,
    )


def main():
    access = pd.read_csv(ACCESS, low_memory=False)
    impact = pd.read_csv(IMPACT, low_memory=False)
    candidate = impact.loc[impact["rank"] == RANK_TO_CHECK].iloc[0]

    drive = load_graph(DRIVE_GRAPH)
    walk = load_graph(WALK_GRAPH)

    drive_pop = access["drive_nearest_node_id"].astype(str).tolist()
    walk_pop = access["walk_nearest_node_id"].astype(str).tolist()

    drive_node = str(candidate["drive_candidate_node_id"])
    walk_node = str(candidate["walk_candidate_node_id"])

    drive_new = candidate_distances(drive, drive_node, drive_pop)
    walk_new = candidate_distances(walk, walk_node, walk_pop)

    drive_before = pd.to_numeric(
        access["driving_distance_m"], errors="coerce"
    ).to_numpy(dtype=float)
    walk_before = pd.to_numeric(
        access["walking_distance_m"], errors="coerce"
    ).to_numpy(dtype=float)

    drive_cross = (
        np.isfinite(drive_before)
        & (drive_before > THRESHOLD_M)
        & np.isfinite(drive_new)
        & (np.minimum(drive_before, drive_new) <= THRESHOLD_M)
    )
    walk_cross = (
        np.isfinite(walk_before)
        & (walk_before > THRESHOLD_M)
        & np.isfinite(walk_new)
        & (np.minimum(walk_before, walk_new) <= THRESHOLD_M)
    )

    same_cross = drive_cross & walk_cross
    either_cross = drive_cross | walk_cross

    print("Candidate:", candidate["candidate_zone_id"])
    print("Driving candidate node:", drive_node)
    print("Walking candidate node:", walk_node)
    print("\nRecomputed threshold crossings:")
    print("Driving:", int(drive_cross.sum()))
    print("Walking:", int(walk_cross.sum()))
    print("Cross in both modes:", int(same_cross.sum()))
    print("Cross in either mode:", int(either_cross.sum()))
    print("Different crossing-cell membership:", int((drive_cross != walk_cross).sum()))

    print("\nCandidate distances available:")
    print("Driving:", int(np.isfinite(drive_new).sum()))
    print("Walking:", int(np.isfinite(walk_new).sum()))

    print("\nCandidate node IDs equal:", drive_node == walk_node)
    print(
        "Candidate nodes exist in graphs:",
        drive_node in drive,
        walk_node in walk,
    )


if __name__ == "__main__":
    main()
