
import heapq
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx
import pandas as pd
import osmnx as ox

ROOT = Path(__file__).resolve().parent.parent
SILVER = ROOT / "data" / "silver"
GOLD = ROOT / "data" / "gold"
RAW = ROOT / "data" / "raw"
REPORTS = ROOT / "reports"

POPULATION_FILE = GOLD / "healthcare_accessibility_by_population_cell.csv"
DRIVE_GRAPH = RAW / "roads_osm_20261011_115925.graphml"
WALK_GRAPH = RAW / "roads_walking_osm_20261011_122708.graphml"

THRESHOLD_M = 5000.0


def latest_file(folder, pattern):
    files = sorted(
        folder.glob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError(f"No file found: {folder / pattern}")
    return files[0]


def node_id(value):
    """Convert CSV node IDs safely to integer/string graph node IDs."""
    if pd.isna(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = str(value).strip()
    try:
        number = float(text)
        if number.is_integer():
            return int(number)
    except ValueError:
        pass
    return text


def edge_length(graph, u, v):
    """Get the shortest available edge length between two nodes."""
    data = graph.get_edge_data(u, v)
    if data is None:
        return None

    # MultiGraph/MultiDiGraph: data is keyed by edge key.
    if graph.is_multigraph():
        values = [
            float(attrs["length"])
            for attrs in data.values()
            if attrs.get("length") is not None
            and math.isfinite(float(attrs["length"]))
            and float(attrs["length"]) >= 0
        ]
    else:
        value = data.get("length")
        values = (
            [float(value)]
            if value is not None
            and math.isfinite(float(value))
            and float(value) >= 0
            else []
        )

    return min(values) if values else None


def nearest_facility_dijkstra(graph, source_nodes):
    """
    Multi-source Dijkstra on a reversed graph.
    Distances then represent directed distance from a population node
    to the nearest education source node in the original graph.

    Returns:
      distances[node] = shortest distance in metres
      origins[node] = nearest source node
    """
    distances = {}
    origins = {}
    heap = []

    for source in source_nodes:
        if source not in graph:
            continue
        if source not in distances:
            distances[source] = 0.0
            origins[source] = source
            heapq.heappush(heap, (0.0, str(source), source))

    while heap:
        distance_u, _, u = heapq.heappop(heap)

        if distance_u != distances.get(u):
            continue

        for v in graph.neighbors(u):
            length = edge_length(graph, u, v)
            if length is None:
                continue

            candidate = distance_u + length
            old = distances.get(v)

            if old is None or candidate < old:
                distances[v] = candidate
                origins[v] = origins[u]
                heapq.heappush(heap, (candidate, str(v), v))

    return distances, origins


def main():
    GOLD.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    if not POPULATION_FILE.exists():
        raise FileNotFoundError(POPULATION_FILE)
    if not DRIVE_GRAPH.exists():
        raise FileNotFoundError(DRIVE_GRAPH)
    if not WALK_GRAPH.exists():
        raise FileNotFoundError(WALK_GRAPH)

    education_file = latest_file(
        SILVER, "education_network_matches_*.csv"
    )

    print("Loading population grid...")
    population = pd.read_csv(POPULATION_FILE)

    required_population = {
        "population_cell_id",
        "raster_row",
        "raster_col",
        "latitude",
        "longitude",
        "population_raster_value",
        "drive_nearest_node_id",
        "walk_nearest_node_id",
    }
    missing = required_population - set(population.columns)
    if missing:
        raise ValueError(
            f"Population file missing columns: {sorted(missing)}"
        )

    print("Loading education network matches...")
    education = pd.read_csv(education_file)

    required_education = {
        "osm_key",
        "name",
        "facility_type",
        "driving_node",
        "walking_node",
        "driving_match_status",
        "walking_match_status",
    }
    missing = required_education - set(education.columns)
    if missing:
        raise ValueError(
            f"Education file missing columns: {sorted(missing)}"
        )

    print("Loading existing road graphs...")
    drive_graph = ox.load_graphml(DRIVE_GRAPH)
    walk_graph = ox.load_graphml(WALK_GRAPH)

    print(
        f"Driving graph: {len(drive_graph):,} nodes, "
        f"{drive_graph.number_of_edges():,} edges"
    )
    print(
        f"Walking graph: {len(walk_graph):,} nodes, "
        f"{walk_graph.number_of_edges():,} edges"
    )

    # Map each snapped source node to a representative education record.
    # When multiple features share a node, prefer a named feature.
    def prepare_sources(mode):
        node_col = f"{mode}_node"
        status_col = f"{mode}_match_status"
        candidates = education.copy()
        candidates["_node"] = candidates[node_col].apply(node_id)

        # Keep only successful network matches; review-snap matches remain
        # usable but are still flagged in the source data.
        candidates = candidates[
            candidates[status_col].isin(
                ["matched", "matched_review_snap"]
            )
            & candidates["_node"].notna()
        ].copy()

        candidates["_has_name"] = (
            candidates["name"].notna()
            & candidates["name"].astype(str).str.strip().ne("")
        )

        candidates = candidates.sort_values(
            ["_has_name", "osm_key"],
            ascending=[False, True],
        )

        representative = {}
        for _, row in candidates.iterrows():
            source_node = row["_node"]
            if source_node not in representative:
                representative[source_node] = {
                    "osm_key": row["osm_key"],
                    "name": (
                        str(row["name"])
                        if pd.notna(row["name"])
                        and str(row["name"]).strip()
                        else None
                    ),
                    "facility_type": (
                        str(row["facility_type"])
                        if pd.notna(row["facility_type"])
                        else None
                    ),
                }
        return representative

    drive_sources = prepare_sources("driving")
    walk_sources = prepare_sources("walking")

    drive_sources_valid = {
        n: meta for n, meta in drive_sources.items()
        if n in drive_graph
    }
    walk_sources_valid = {
        n: meta for n, meta in walk_sources.items()
        if n in walk_graph
    }

    if not drive_sources_valid:
        raise ValueError("No valid Education source nodes in driving graph")
    if not walk_sources_valid:
        raise ValueError("No valid Education source nodes in walking graph")

    print(
        f"Unique education source nodes — driving: "
        f"{len(drive_sources_valid):,}; walking: "
        f"{len(walk_sources_valid):,}"
    )

    # Reverse the directed graphs so multi-source Dijkstra gives
    # distance from each population node TO a facility in the original graph.
    print("Calculating driving network distances...")
    drive_reverse = drive_graph.reverse(copy=False)
    drive_distances, drive_origins = nearest_facility_dijkstra(
        drive_reverse, drive_sources_valid.keys()
    )

    print("Calculating walking network distances...")
    walk_reverse = walk_graph.reverse(copy=False)
    walk_distances, walk_origins = nearest_facility_dijkstra(
        walk_reverse, walk_sources_valid.keys()
    )

    # Population-grid node IDs are already snapped to these same graphs.
    drive_population_nodes = population[
        "drive_nearest_node_id"
    ].apply(node_id)
    walk_population_nodes = population[
        "walk_nearest_node_id"
    ].apply(node_id)

    result = population[
        [
            "population_cell_id",
            "raster_row",
            "raster_col",
            "latitude",
            "longitude",
            "population_raster_value",
        ]
    ].copy()

    result["driving_distance_m"] = drive_population_nodes.map(
        drive_distances
    )
    result["walking_distance_m"] = walk_population_nodes.map(
        walk_distances
    )

    result["driving_nearest_source_node"] = drive_population_nodes.map(
        drive_origins
    )
    result["walking_nearest_source_node"] = walk_population_nodes.map(
        walk_origins
    )

    result["driving_reachable"] = result["driving_distance_m"].notna()
    result["walking_reachable"] = result["walking_distance_m"].notna()

    result["driving_within_5km"] = (
        result["driving_distance_m"].notna()
        & (result["driving_distance_m"] <= THRESHOLD_M)
    )
    result["walking_within_5km"] = (
        result["walking_distance_m"].notna()
        & (result["walking_distance_m"] <= THRESHOLD_M)
    )

    result["driving_nearest_facility_id"] = (
        result["driving_nearest_source_node"].map(
            lambda n: drive_sources_valid.get(n, {}).get("osm_key")
        )
    )
    result["driving_nearest_facility_name"] = (
        result["driving_nearest_source_node"].map(
            lambda n: drive_sources_valid.get(n, {}).get("name")
        )
    )
    result["driving_nearest_facility_category"] = (
        result["driving_nearest_source_node"].map(
            lambda n: drive_sources_valid.get(n, {}).get("facility_type")
        )
    )

    result["walking_nearest_facility_id"] = (
        result["walking_nearest_source_node"].map(
            lambda n: walk_sources_valid.get(n, {}).get("osm_key")
        )
    )
    result["walking_nearest_facility_name"] = (
        result["walking_nearest_source_node"].map(
            lambda n: walk_sources_valid.get(n, {}).get("name")
        )
    )
    result["walking_nearest_facility_category"] = (
        result["walking_nearest_source_node"].map(
            lambda n: walk_sources_valid.get(n, {}).get("facility_type")
        )
    )

    result["driving_source_node_valid"] = drive_population_nodes.isin(
        drive_graph.nodes
    )
    result["walking_source_node_valid"] = walk_population_nodes.isin(
        walk_graph.nodes
    )

    # Summary statistics. These describe mapped-feature distances only.
    def mode_summary(distance_col, reachable_col, within_col):
        distances = pd.to_numeric(result[distance_col], errors="coerce")
        reachable = result[reachable_col]
        valid = distances[reachable]

        return {
            "reachable_cells": int(reachable.sum()),
            "unreachable_cells": int((~reachable).sum()),
            "within_5km_cells": int(result[within_col].sum()),
            "over_5km_reachable_cells": int(
                (reachable & (distances > THRESHOLD_M)).sum()
            ),
            "median_distance_m": (
                float(valid.median()) if len(valid) else None
            ),
            "mean_distance_m": (
                float(valid.mean()) if len(valid) else None
            ),
            "p90_distance_m": (
                float(valid.quantile(0.90)) if len(valid) else None
            ),
            "max_distance_m": (
                float(valid.max()) if len(valid) else None
            ),
        }

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_csv = GOLD / f"education_accessibility_by_population_cell_{timestamp}.csv"
    summary_json = REPORTS / f"education_accessibility_summary_{timestamp}.json"

    result.to_csv(output_csv, index=False, encoding="utf-8-sig")

    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "population_source": str(
            POPULATION_FILE.relative_to(ROOT)
        ),
        "education_source": str(education_file.relative_to(ROOT)),
        "driving_graph": str(DRIVE_GRAPH.relative_to(ROOT)),
        "walking_graph": str(WALK_GRAPH.relative_to(ROOT)),
        "output_file": str(output_csv.relative_to(ROOT)),
        "population_cells": int(len(result)),
        "education_records_in_source": int(len(education)),
        "unique_driving_source_nodes": int(len(drive_sources_valid)),
        "unique_walking_source_nodes": int(len(walk_sources_valid)),
        "threshold_m": THRESHOLD_M,
        "driving": mode_summary(
            "driving_distance_m",
            "driving_reachable",
            "driving_within_5km",
        ),
        "walking": mode_summary(
            "walking_distance_m",
            "walking_reachable",
            "walking_within_5km",
        ),
        "invalid_population_driving_nodes": int(
            (~result["driving_source_node_valid"]).sum()
        ),
        "invalid_population_walking_nodes": int(
            (~result["walking_source_node_valid"]).sum()
        ),
        "limitations": [
            "Distances are network lengths in metres, not travel times.",
            "The 5 km threshold is preliminary and not an official standard.",
            "OSM education features may include campus blocks or sub-features.",
            "Multiple mapped features can share a road node.",
            "Raster population values have not been verified as headcounts.",
            "This analysis is not independent validation of real-world access.",
        ],
    }

    with summary_json.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 64)
    print("EDUCATION ACCESSIBILITY SUMMARY")
    print("=" * 64)
    print(f"Population cells: {len(result):,}")
    print(f"Education source nodes: drive={len(drive_sources_valid):,}, "
          f"walk={len(walk_sources_valid):,}")

    for mode in ("driving", "walking"):
        stats = summary[mode]
        print(f"\n{mode.upper()}")
        print(f"  Reachable: {stats['reachable_cells']:,}")
        print(f"  Unreachable: {stats['unreachable_cells']:,}")
        print(f"  Within 5 km: {stats['within_5km_cells']:,}")
        print(f"  Over 5 km (reachable): {stats['over_5km_reachable_cells']:,}")
        print(f"  Median distance: {stats['median_distance_m']}")
        print(f"  Mean distance: {stats['mean_distance_m']}")
        print(f"  P90 distance: {stats['p90_distance_m']}")

    print(f"\nOutput CSV: {output_csv}")
    print(f"Summary JSON: {summary_json}")
    print("\nExisting healthcare files and road graphs were not modified.")


if __name__ == "__main__":
    main()
