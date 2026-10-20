
from pathlib import Path
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import networkx as nx
import osmnx as ox
from pyproj import Geod

ROOT = Path(__file__).resolve().parents[1]

ACCESS = ROOT / "data/gold/healthcare_accessibility_by_population_cell.csv"
CANDIDATES = ROOT / "data/gold/healthcare_candidate_sites.csv"
DRIVE_GRAPH = ROOT / "data/raw/roads_osm_20261011_115925.graphml"
WALK_GRAPH = ROOT / "data/raw/roads_walking_osm_20261011_122708.graphml"

OUT_CSV = ROOT / "reports/candidate_impact_top10_20261012.csv"
OUT_JSON = ROOT / "reports/candidate_impact_top10_20261012_summary.json"

TOP_N = 10
THRESHOLD_M = 5000.0
SNAP_WARNING_M = 250.0
GEOD = Geod(ellps="WGS84")


def load_graph(path):
    if not path.exists():
        raise FileNotFoundError(f"Missing graph: {path}")
    graph = ox.load_graphml(path)
    graph = nx.relabel_nodes(graph, lambda n: str(n), copy=True)

    for _, _, _, data in graph.edges(keys=True, data=True):
        length = float(data.get("length", np.nan))
        if not np.isfinite(length) or length <= 0:
            raise ValueError(f"Invalid edge length in {path.name}")
        data["length"] = length
    return graph


def snap_candidates(graph, candidates):
    coords = list(zip(
        candidates["centroid_longitude"].astype(float),
        candidates["centroid_latitude"].astype(float),
    ))
    xs = np.array([p[0] for p in coords])
    ys = np.array([p[1] for p in coords])
    nodes = [str(n) for n in np.atleast_1d(
        ox.distance.nearest_nodes(graph, X=xs, Y=ys)
    )]

    distances = []
    for (_, row), node in zip(candidates.iterrows(), nodes):
        _, _, metres = GEOD.inv(
            float(row["centroid_longitude"]),
            float(row["centroid_latitude"]),
            float(graph.nodes[node]["x"]),
            float(graph.nodes[node]["y"]),
        )
        distances.append(abs(float(metres)))
    return nodes, distances


def distances_to_candidate(graph, candidate_node, population_nodes):
    # Reversing the directed graph makes the single-source search calculate
    # distances from each population node TO the candidate in the original graph.
    reverse_graph = graph.reverse(copy=False)
    dist = nx.single_source_dijkstra_path_length(
        reverse_graph, candidate_node, weight="length"
    )
    return np.array([dist.get(n, np.nan) for n in population_nodes], dtype=float)


def mode_summary(baseline, new_distance, raster_values):
    baseline = np.asarray(baseline, dtype=float)
    new_distance = np.asarray(new_distance, dtype=float)

    # A new facility cannot worsen shortest-path distance.
    after = np.fmin(baseline, new_distance)
    before_reachable = np.isfinite(baseline)
    after_reachable = np.isfinite(after)
    newly_reached = ~before_reachable & after_reachable

    both = before_reachable & np.isfinite(new_distance)
    improvement = np.zeros(len(baseline), dtype=float)
    improvement[both] = baseline[both] - after[both]

    before_over = before_reachable & (baseline > THRESHOLD_M)
    after_over = after_reachable & (after > THRESHOLD_M)

    weights = np.asarray(raster_values, dtype=float)
    valid_weights = np.isfinite(weights) & (weights >= 0)

    def weighted_mean(values):
        mask = np.isfinite(values) & valid_weights
        if not mask.any() or weights[mask].sum() <= 0:
            return None
        return float(np.average(values[mask], weights=weights[mask]))

    def mean_or_none(values):
        values = values[np.isfinite(values)]
        return float(values.mean()) if len(values) else None

    return {
        "reachable_before": int(before_reachable.sum()),
        "reachable_after": int(after_reachable.sum()),
        "newly_reachable": int(newly_reached.sum()),
        "cells_improved_over_1m": int((improvement > 1.0).sum()),
        "mean_distance_before_m": mean_or_none(baseline),
        "mean_distance_after_m": mean_or_none(after),
        "mean_reduction_among_baseline_reachable_m": mean_or_none(
            np.where(both, improvement, np.nan)
        ),
        "cells_over_5km_before": int(before_over.sum()),
        "cells_over_5km_after": int(after_over.sum()),
        "cells_moved_to_5km_or_less": int(
            (before_over & after_reachable & (after <= THRESHOLD_M)).sum()
        ),
        "raster_proxy_weighted_mean_before_m": weighted_mean(baseline),
        "raster_proxy_weighted_mean_after_m": weighted_mean(after),
    }


def main():
    for path in [ACCESS, CANDIDATES, DRIVE_GRAPH, WALK_GRAPH]:
        if not path.exists():
            raise FileNotFoundError(f"Missing input: {path}")

    access = pd.read_csv(ACCESS, low_memory=False)
    candidates = pd.read_csv(CANDIDATES, low_memory=False)
    candidates = candidates.nsmallest(TOP_N, "rank").reset_index(drop=True)

    required_access = [
        "drive_nearest_node_id", "walk_nearest_node_id",
        "driving_distance_m", "walking_distance_m",
        "population_raster_value",
    ]
    required_candidates = [
        "rank", "candidate_zone_id",
        "centroid_latitude", "centroid_longitude",
    ]
    for col in required_access:
        if col not in access:
            raise ValueError(f"Missing accessibility column: {col}")
    for col in required_candidates:
        if col not in candidates:
            raise ValueError(f"Missing candidate column: {col}")

    print(f"Population cells: {len(access):,}")
    print(f"Candidates to simulate: {len(candidates)}")

    drive = load_graph(DRIVE_GRAPH)
    walk = load_graph(WALK_GRAPH)

    drive_pop = access["drive_nearest_node_id"].astype(str).tolist()
    walk_pop = access["walk_nearest_node_id"].astype(str).tolist()

    missing_drive = sum(n not in drive for n in drive_pop)
    missing_walk = sum(n not in walk for n in walk_pop)
    if missing_drive or missing_walk:
        raise ValueError(
            f"Population nodes missing from graph: drive={missing_drive}, "
            f"walk={missing_walk}. No outputs written."
        )

    drive_nodes, drive_snaps = snap_candidates(drive, candidates)
    walk_nodes, walk_snaps = snap_candidates(walk, candidates)
    raster = pd.to_numeric(
        access["population_raster_value"], errors="coerce"
    ).to_numpy(dtype=float)

    rows = []
    for i, candidate in candidates.iterrows():
        cid = str(candidate["candidate_zone_id"])
        dn, wn = drive_nodes[i], walk_nodes[i]
        print(f"Simulating rank {int(candidate['rank'])}: {cid}")

        drive_new = distances_to_candidate(drive, dn, drive_pop)
        walk_new = distances_to_candidate(walk, wn, walk_pop)

        ds = mode_summary(
            pd.to_numeric(access["driving_distance_m"], errors="coerce"),
            drive_new, raster
        )
        ws = mode_summary(
            pd.to_numeric(access["walking_distance_m"], errors="coerce"),
            walk_new, raster
        )

        row = {
            "rank": int(candidate["rank"]),
            "candidate_zone_id": cid,
            "centroid_latitude": float(candidate["centroid_latitude"]),
            "centroid_longitude": float(candidate["centroid_longitude"]),
            "drive_candidate_node_id": dn,
            "walk_candidate_node_id": wn,
            "drive_candidate_snap_m": round(drive_snaps[i], 2),
            "walk_candidate_snap_m": round(walk_snaps[i], 2),
            "drive_snap_review": drive_snaps[i] > SNAP_WARNING_M,
            "walk_snap_review": walk_snaps[i] > SNAP_WARNING_M,
        }

        for prefix, summary in [("driving", ds), ("walking", ws)]:
            for key, value in summary.items():
                row[f"{prefix}_{key}"] = value
        rows.append(row)

    result = pd.DataFrame(rows)
    result["simulation_scope"] = "Each candidate added individually; candidates are not combined."
    result["population_raster_units_verified"] = False
    result["candidate_is_buildable_parcel"] = False
    result["travel_time_modelled"] = False
    result["facility_capacity_modelled"] = False

    summary = {
        "title": "AURIS-X top-10 healthcare candidate impact diagnostic",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_count": len(result),
        "population_cell_count": len(access),
        "distance_units": "Directed road-network metres, not travel time.",
        "scope": "Each candidate tested individually against the existing facility baseline.",
        "population_raster_units_verified": False,
        "candidate_parcel_suitability_verified": False,
        "facility_capacity_modelled": False,
        "limitations": [
            "Candidate centroids are proxy locations, not verified facility parcels or entrances.",
            "Road-node snapping does not prove practical access.",
            "Raster units are unverified; weighted results are proxies, not population headcounts.",
            "No facility capacity, service mix, traffic, travel-time, or site cost is modelled.",
            "Each candidate is tested alone; interactions among multiple new sites are not modelled.",
            "OSM facility operational status and real-world network accuracy are not independently verified.",
        ],
        "output_csv": str(OUT_CSV),
        "output_json": str(OUT_JSON),
    }

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUT_CSV, index=False)
    OUT_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\nSimulation complete.")
    print(f"CSV: {OUT_CSV}")
    print(f"Summary: {OUT_JSON}")
    print("\nTop 10 impact comparison:")
    print(result[[
        "rank", "candidate_zone_id",
        "driving_cells_moved_to_5km_or_less",
        "walking_cells_moved_to_5km_or_less",
        "driving_cells_improved_over_1m",
        "walking_cells_improved_over_1m",
        "drive_candidate_snap_m", "walk_candidate_snap_m",
    ]].to_string(index=False))


if __name__ == "__main__":
    main()
