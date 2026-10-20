from pathlib import Path
import argparse
import json
import math
from datetime import datetime, timezone

import networkx as nx
import osmnx as ox
import pandas as pd


def find_column(df, options, description):
    for name in options:
        if name in df.columns:
            return name
    raise ValueError(
        f"Cannot find {description}. Available columns: {list(df.columns)}"
    )


def node_key(value):
    if pd.isna(value):
        return None
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def graph_distances_to_any_site(graph, site_nodes):
    # Reverse directed edges so a multi-source search calculates distance
    # from every network node TO its nearest selected site in the original graph.
    reverse_graph = graph.reverse(copy=False) if graph.is_directed() else graph
    lengths = nx.multi_source_dijkstra_path_length(
        reverse_graph, set(site_nodes), weight="length"
    )
    return {node_key(k): float(v) for k, v in lengths.items()}



def haversine_m(lat1, lon1, lat2, lon2):
    """Approximate straight-line distance in metres between two coordinates."""
    radius_m = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius_m * math.asin(min(1.0, math.sqrt(a)))

def main():
    parser = argparse.ArgumentParser(
        description="Joint driving/walking accessibility simulation for a site portfolio."
    )
    parser.add_argument(
        "--site-ids",
        required=True,
        help="Comma-separated candidate_zone_id values from the healthcare candidate CSV.",
    )
    parser.add_argument("--improvement-threshold-m", type=float, default=1.0)
    parser.add_argument("--reachability-threshold-m", type=float, default=5000.0)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    site_ids = [x.strip() for x in args.site_ids.split(",") if x.strip()]
    if not site_ids:
        raise SystemExit("Supply at least one --site-ids value.")
    if len(set(site_ids)) != len(site_ids):
        raise SystemExit("Duplicate site IDs supplied.")
    if args.improvement_threshold_m < 0 or args.reachability_threshold_m <= 0:
        raise SystemExit("Distance thresholds must be non-negative; reachability must be positive.")

    candidate_path = root / "data" / "gold" / "healthcare_candidate_sites.csv"
    cells_path = root / "data" / "gold" / "healthcare_accessibility_by_population_cell.csv"
    drive_graph_path = root / "data" / "raw" / "roads_osm_20261011_115925.graphml"
    walk_graph_path = root / "data" / "raw" / "roads_walking_osm_20261011_120504.graphml"

    for path in [candidate_path, cells_path, drive_graph_path, walk_graph_path]:
        if not path.exists():
            raise SystemExit(f"Required input not found: {path}")

    candidates = pd.read_csv(candidate_path)
    id_col = find_column(candidates, ["candidate_zone_id"], "candidate site ID")
    lat_col = find_column(
        candidates,
        ["centroid_lat", "centroid_latitude", "latitude", "lat"],
        "candidate latitude",
    )
    lon_col = find_column(
        candidates,
        ["centroid_lon", "centroid_longitude", "longitude", "lon", "lng"],
        "candidate longitude",
    )
    chosen = candidates[candidates[id_col].astype(str).isin(site_ids)].copy()
    found_ids = set(chosen[id_col].astype(str))
    missing_ids = [x for x in site_ids if x not in found_ids]
    if missing_ids:
        raise SystemExit(f"Unknown candidate site IDs: {missing_ids}")
    if len(chosen) != len(site_ids):
        raise SystemExit("Candidate IDs are not unique; refusing ambiguous site selection.")
    if chosen[[lat_col, lon_col]].isna().any().any():
        raise SystemExit("One or more selected candidates has missing coordinates.")

    cells = pd.read_csv(cells_path)
    drive_node_col = find_column(
        cells, ["drive_nearest_node_id", "driving_nearest_node_id"],
        "baseline driving nearest-node column",
    )
    walk_node_col = find_column(
        cells, ["walk_nearest_node_id", "walking_nearest_node_id"],
        "baseline walking nearest-node column",
    )
    drive_base_col = find_column(
        cells, ["driving_distance_m", "drive_distance_m"],
        "baseline driving distance column",
    )
    walk_base_col = find_column(
        cells, ["walking_distance_m", "walk_distance_m"],
        "baseline walking distance column",
    )

    drive_graph = ox.load_graphml(drive_graph_path)
    walk_graph = ox.load_graphml(walk_graph_path)

    drive_site_nodes = []
    walk_site_nodes = []
    snapped = []
    for _, site in chosen.iterrows():
        lat, lon = float(site[lat_col]), float(site[lon_col])
        drive_node = ox.distance.nearest_nodes(drive_graph, X=lon, Y=lat)
        walk_node = ox.distance.nearest_nodes(walk_graph, X=lon, Y=lat)
        drive_snap_m = haversine_m(
            lat, lon,
            float(drive_graph.nodes[drive_node]["y"]),
            float(drive_graph.nodes[drive_node]["x"]),
        )
        walk_snap_m = haversine_m(
            lat, lon,
            float(walk_graph.nodes[walk_node]["y"]),
            float(walk_graph.nodes[walk_node]["x"]),
        )
        drive_site_nodes.append(drive_node)
        walk_site_nodes.append(walk_node)
        snapped.append({
            "candidate_zone_id": str(site[id_col]),
            "latitude": lat,
            "longitude": lon,
            "driving_graph_node": str(drive_node),
            "walking_graph_node": str(walk_node),
            "driving_snap_distance_approx_m": round(drive_snap_m, 2),
            "walking_snap_distance_approx_m": round(walk_snap_m, 2),
            "buildable_land_verified": False,
        })

    drive_to_site = graph_distances_to_any_site(drive_graph, drive_site_nodes)
    walk_to_site = graph_distances_to_any_site(walk_graph, walk_site_nodes)

    cells["baseline_driving_distance_m"] = pd.to_numeric(cells[drive_base_col], errors="coerce")
    cells["baseline_walking_distance_m"] = pd.to_numeric(cells[walk_base_col], errors="coerce")
    # Keep proposed-site-only distances for auditability.
    cells["proposed_sites_driving_distance_m"] = cells[drive_node_col].map(
        lambda x: drive_to_site.get(node_key(x), math.nan)
    )
    cells["proposed_sites_walking_distance_m"] = cells[walk_node_col].map(
        lambda x: walk_to_site.get(node_key(x), math.nan)
    )

    # Adding sites cannot remove access to existing facilities.
    # Combined distance is the better of baseline access and proposed-site access.
    cells["portfolio_driving_distance_m"] = pd.concat(
        [
            cells["baseline_driving_distance_m"],
            cells["proposed_sites_driving_distance_m"],
        ],
        axis=1,
    ).min(axis=1, skipna=True)
    cells["portfolio_walking_distance_m"] = pd.concat(
        [
            cells["baseline_walking_distance_m"],
            cells["proposed_sites_walking_distance_m"],
        ],
        axis=1,
    ).min(axis=1, skipna=True)

    threshold = args.reachability_threshold_m
    improvement = args.improvement_threshold_m
    metrics = {}
    for mode in ["driving", "walking"]:
        base = cells[f"baseline_{mode}_distance_m"]
        new = cells[f"portfolio_{mode}_distance_m"]
        valid = base.notna() & new.notna()
        delta = base - new
        baseline_reachable = valid & (base <= threshold)
        metrics[mode] = {
            "grid_cells_with_baseline_and_portfolio_routes": int(valid.sum()),
            "grid_cells_improved_over_threshold": int((valid & (delta > improvement)).sum()),
            "grid_cells_moved_to_within_reachability_threshold": int(
                (valid & (base > threshold) & (new <= threshold)).sum()
            ),
            "grid_cells_within_threshold_after_portfolio": int(
                (valid & (new <= threshold)).sum()
            ),
            "mean_baseline_distance_m_among_baseline_reachable": (
                round(float(base[baseline_reachable].mean()), 3)
                if baseline_reachable.any() else None
            ),
            "mean_portfolio_distance_m_among_baseline_reachable": (
                round(float(new[baseline_reachable].mean()), 3)
                if baseline_reachable.any() else None
            ),
            "mean_distance_reduction_m_among_baseline_reachable": (
                round(float(delta[baseline_reachable].mean()), 3)
                if baseline_reachable.any() else None
            ),
            "mean_baseline_distance_m_all_comparable_cells": (
                round(float(base[valid].mean()), 3) if valid.any() else None
            ),
            "mean_portfolio_distance_m_all_comparable_cells": (
                round(float(new[valid].mean()), 3) if valid.any() else None
            ),
            "mean_distance_reduction_m_all_comparable_cells": (
                round(float(delta[valid].mean()), 3) if valid.any() else None
            ),
            "unrouted_or_missing_cells": int((~valid).sum()),
        }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    detail_path = reports / f"healthcare_portfolio_cells_{stamp}.csv"
    summary_path = reports / f"healthcare_portfolio_impact_{stamp}.json"

    keep_cols = list(dict.fromkeys([
        drive_node_col, walk_node_col, drive_base_col, walk_base_col,
        "baseline_driving_distance_m", "proposed_sites_driving_distance_m",
        "portfolio_driving_distance_m",
        "baseline_walking_distance_m", "proposed_sites_walking_distance_m",
        "portfolio_walking_distance_m",
    ]))
    if "population_raster_value" in cells.columns:
        keep_cols.append("population_raster_value")
    cells[keep_cols].to_csv(detail_path, index=False)

    summary = {
        "status": "PASS",
        "method": "Joint multi-source shortest-path calculation to the nearest selected site",
        "created_utc": stamp,
        "selected_site_count": len(chosen),
        "selected_site_ids": [str(x) for x in chosen[id_col]],
        "selected_sites": snapped,
        "input_grid_cell_count": len(cells),
        "improvement_threshold_m": improvement,
        "reachability_threshold_m": threshold,
        "metrics": metrics,
        "outputs": {
            "detail_csv": str(detail_path.relative_to(root)),
            "summary_json": str(summary_path.relative_to(root)),
        },
        "limitations": [
            "Results are based on the supplied road graphs and grid-cell nearest-node assignments.",
            "Grid-cell counts are not counts of people; population raster units remain unverified.",
            "Candidate centroids are not surveyed or verified buildable parcels.",
            "Network snapping distances are approximate straight-line distances to graph nodes.",
            "Travel time, facility capacity, land availability, costs, and operational constraints are not modelled.",
            "This is a joint nearest-site accessibility calculation; it does not assume individual site impacts are additive.",
            "A route to a selected site is treated as access to that site regardless of capacity or service eligibility.",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
