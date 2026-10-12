
from pathlib import Path
import json
import glob
import os

import pandas as pd
import rasterio
import osmnx as ox
import networkx as nx

ROOT = Path(__file__).resolve().parent.parent


def latest(pattern):
    files = glob.glob(str(ROOT / pattern))
    if not files:
        raise FileNotFoundError(f"No files found for pattern: {pattern}")
    return Path(max(files, key=os.path.getmtime))


def main():
    matches_path = latest("data/silver/healthcare_network_matches_*.csv")
    drive_path = latest("data/raw/roads_osm_*.graphml")
    walk_path = latest("data/raw/roads_walking_osm_*.graphml")
    population_path = (
        ROOT / "data" / "population" / "coimbatore_population_2026_approx.tif"
    )

    matches = pd.read_csv(matches_path)

    with rasterio.open(population_path) as src:
        pop_data = src.read(1, masked=True)
        valid = pop_data.compressed()
        positive_count = int((valid > 0).sum())

    drive_graph = ox.load_graphml(drive_path)
    walk_graph = ox.load_graphml(walk_path)

    drive_facility_ids = set(matches["drive_nearest_node_id"].dropna().astype(str))
    walk_facility_ids = set(matches["walk_nearest_node_id"].dropna().astype(str))

    drive_node_ids = {str(n) for n in drive_graph.nodes}
    walk_node_ids = {str(n) for n in walk_graph.nodes}

    report = {
        "healthcare_matches_file": str(matches_path),
        "driving_graph_file": str(drive_path),
        "walking_graph_file": str(walk_path),
        "population_raster_file": str(population_path),
        "healthcare_rows": int(len(matches)),
        "unique_healthcare_osm_ids": int(matches["osm_id"].nunique()),
        "population_valid_cells": int(valid.size),
        "population_positive_cells": positive_count,
        "driving_graph_nodes": int(drive_graph.number_of_nodes()),
        "driving_graph_edges": int(drive_graph.number_of_edges()),
        "walking_graph_nodes": int(walk_graph.number_of_nodes()),
        "walking_graph_edges": int(walk_graph.number_of_edges()),
        "driving_facility_node_ids_found": int(
            sum(node in drive_node_ids for node in drive_facility_ids)
        ),
        "walking_facility_node_ids_found": int(
            sum(node in walk_node_ids for node in walk_facility_ids)
        ),
        "important_note": (
            "This is an input audit, not an accessibility result. "
            "Facility node ID matching and population-to-network snapping "
            "must be checked before calculating shortest paths."
        ),
    }

    output = ROOT / "reports" / "access_inputs_inspection.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("ACCESS INPUT INSPECTION COMPLETE")
    print(json.dumps(report, indent=2))
    print(f"\nReport saved to: {output}")


if __name__ == "__main__":
    main()
