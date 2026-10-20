from pathlib import Path
from datetime import datetime, timezone
import argparse
import json

import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
from pyproj import Geod

ROOT = Path(__file__).resolve().parents[1]
ACCESS = ROOT / "data/gold/healthcare_accessibility_by_population_cell.csv"
DRIVE_GRAPH = ROOT / "data/raw/roads_osm_20261011_115925.graphml"
WALK_GRAPH = ROOT / "data/raw/roads_walking_osm_20261011_122708.graphml"
OUT_DIR = ROOT / "reports"
GEOD = Geod(ellps="WGS84")
THRESHOLD_M = 5000.0


def node_id(value):
    if pd.isna(value):
        return None
    if isinstance(value, (float, np.floating)) and value.is_integer():
        return str(int(value))
    return str(value)


def load_graph(path):
    graph = ox.load_graphml(path)
    graph = nx.relabel_nodes(graph, {n: str(n) for n in graph.nodes})
    if not graph.is_directed():
        raise ValueError(f"Expected a directed road graph: {path}")
    return graph


def nearest_node_and_snap(graph, latitude, longitude):
    nearest = str(ox.distance.nearest_nodes(
        graph, X=float(longitude), Y=float(latitude)
    ))
    node = graph.nodes[nearest]
    _, _, distance = GEOD.inv(
        float(longitude), float(latitude),
        float(node["x"]), float(node["y"])
    )
    return nearest, float(distance)


def network_distances(graph, site_node, population_nodes):
    # Reverse the graph so one Dijkstra run gives distances from every
    # population node TO the proposed facility in the original graph.
    reverse_graph = graph.reverse(copy=False)
    lengths = nx.single_source_dijkstra_path_length(
        reverse_graph, source=site_node, weight="length"
    )
    return np.array(
        [lengths.get(n, np.nan) if n is not None else np.nan
         for n in population_nodes],
        dtype=float
    )


def summarize(mode, baseline, proposed, raster_values):
    baseline = np.asarray(baseline, dtype=float)
    proposed = np.asarray(proposed, dtype=float)
    valid_baseline = np.isfinite(baseline)
    valid_proposed = np.isfinite(proposed)
    valid_both = valid_baseline & valid_proposed

    # A proposed site cannot worsen the nearest-facility baseline.
    after = baseline.copy()
    after[valid_proposed] = np.where(
        valid_baseline[valid_proposed],
        np.minimum(baseline[valid_proposed], proposed[valid_proposed]),
        proposed[valid_proposed]
    )

    improved = valid_both & ((baseline - after) > 1.0)
    before_reachable = valid_baseline
    after_reachable = np.isfinite(after)
    before_over = valid_baseline & (baseline > THRESHOLD_M)
    after_over = after_reachable & (after > THRESHOLD_M)

    result = {
        "mode": mode,
        "grid_cells_evaluated": int(len(baseline)),
        "baseline_reachable_cells": int(before_reachable.sum()),
        "after_reachable_cells": int(after_reachable.sum()),
        "cells_improved_over_1m": int(improved.sum()),
        "mean_distance_before_m": (
            float(np.nanmean(baseline[valid_baseline]))
            if valid_baseline.any() else None
        ),
        "mean_distance_after_m": (
            float(np.nanmean(after[after_reachable]))
            if after_reachable.any() else None
        ),
        "mean_reduction_among_baseline_reachable_m": (
            float(np.mean(baseline[valid_baseline] - after[valid_baseline]))
            if valid_baseline.any() else None
        ),
        "cells_over_5km_before": int(before_over.sum()),
        "cells_over_5km_after": int(after_over.sum()),
        "cells_moved_to_5km_or_less": int(
            (before_over & after_reachable & (after <= THRESHOLD_M)).sum()
        ),
        "population_units_verified": False,
        "note": "Counts refer to grid cells, not verified people."
    }
    return after, result


def main():
    parser = argparse.ArgumentParser(
        description="Fresh healthcare accessibility impact for a proposed coordinate."
    )
    parser.add_argument("--latitude", type=float, required=True)
    parser.add_argument("--longitude", type=float, required=True)
    args = parser.parse_args()

    if not (-90 <= args.latitude <= 90 and -180 <= args.longitude <= 180):
        raise ValueError("Latitude/longitude are outside valid ranges.")

    for path in (ACCESS, DRIVE_GRAPH, WALK_GRAPH):
        if not path.exists():
            raise FileNotFoundError(path)

    print("Loading baseline accessibility cells...")
    df = pd.read_csv(ACCESS)
    required = [
        "drive_nearest_node_id", "walk_nearest_node_id",
        "driving_distance_m", "walking_distance_m",
        "population_raster_value"
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Accessibility file missing columns: {missing}")

    drive_nodes = [node_id(v) for v in df["drive_nearest_node_id"]]
    walk_nodes = [node_id(v) for v in df["walk_nearest_node_id"]]
    drive_baseline = pd.to_numeric(df["driving_distance_m"], errors="coerce").to_numpy(float)
    walk_baseline = pd.to_numeric(df["walking_distance_m"], errors="coerce").to_numpy(float)

    print("Loading driving network...")
    drive_graph = load_graph(DRIVE_GRAPH)
    drive_site, drive_snap = nearest_node_and_snap(
        drive_graph, args.latitude, args.longitude
    )
    missing_drive = sorted({n for n in drive_nodes if n is not None and n not in drive_graph})
    if missing_drive:
        raise ValueError(
            f"{len(missing_drive)} baseline driving nodes are absent from the graph; "
            f"first examples: {missing_drive[:5]}"
        )
    print("Calculating driving distances...")
    drive_proposed = network_distances(drive_graph, drive_site, drive_nodes)
    drive_after, drive_summary = summarize(
        "driving", drive_baseline, drive_proposed, df["population_raster_value"]
    )
    del drive_graph

    print("Loading walking network...")
    walk_graph = load_graph(WALK_GRAPH)
    walk_site, walk_snap = nearest_node_and_snap(
        walk_graph, args.latitude, args.longitude
    )
    missing_walk = sorted({n for n in walk_nodes if n is not None and n not in walk_graph})
    if missing_walk:
        raise ValueError(
            f"{len(missing_walk)} baseline walking nodes are absent from the graph; "
            f"first examples: {missing_walk[:5]}"
        )
    print("Calculating walking distances...")
    walk_proposed = network_distances(walk_graph, walk_site, walk_nodes)
    walk_after, walk_summary = summarize(
        "walking", walk_baseline, walk_proposed, df["population_raster_value"]
    )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / f"proposed_healthcare_location_cells_{stamp}.csv"
    json_path = OUT_DIR / f"proposed_healthcare_location_impact_{stamp}.json"

    details = pd.DataFrame({
        "baseline_driving_distance_m": drive_baseline,
        "proposed_site_driving_distance_m": drive_proposed,
        "driving_distance_after_m": drive_after,
        "baseline_walking_distance_m": walk_baseline,
        "proposed_site_walking_distance_m": walk_proposed,
        "walking_distance_after_m": walk_after,
        "population_raster_value_unverified": df["population_raster_value"]
    })
    for column in ("latitude", "longitude", "cell_id", "population_cell_id"):
        if column in df.columns:
            details.insert(0, column, df[column])
    details.to_csv(csv_path, index=False)

    report = {
        "status": "PASS",
        "simulation_type": "fresh_network_distance_simulation",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "proposed_location": {
            "latitude": args.latitude,
            "longitude": args.longitude
        },
        "snapping": {
            "driving_network_node": drive_site,
            "driving_snap_distance_m": drive_snap,
            "walking_network_node": walk_site,
            "walking_snap_distance_m": walk_snap,
            "warning_threshold_m": 250.0,
            "review_required": drive_snap > 250 or walk_snap > 250
        },
        "driving": drive_summary,
        "walking": walk_summary,
        "inputs": {
            "accessibility_cells": str(ACCESS.relative_to(ROOT)),
            "driving_graph": str(DRIVE_GRAPH.relative_to(ROOT)),
            "walking_graph": str(WALK_GRAPH.relative_to(ROOT)),
            "grid_cell_count": int(len(df))
        },
        "limitations": [
            "Results are fresh network-distance calculations, not travel-time estimates.",
            "Grid cells are not people; population raster units remain unverified.",
            "A graph snap is not proof that the coordinate is buildable land.",
            "Facility capacity, land ownership, construction cost, and service demand are not modelled.",
            "Results depend on the completeness and directionality of the supplied road graphs.",
            "The simulation assumes the proposed facility becomes an additional option and uses the minimum of baseline and proposed-site distance."
        ],
        "detail_csv": str(csv_path.relative_to(ROOT))
    }
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nDetailed cell results: {csv_path}")
    print(f"Impact report: {json_path}")


if __name__ == "__main__":
    main()
