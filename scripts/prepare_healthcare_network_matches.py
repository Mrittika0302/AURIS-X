
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import osmnx as ox
import pandas as pd

# --------------------------------------------------
# AURIS-X: Healthcare-to-road-network preparation
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
SILVER = ROOT / "data" / "silver"
REPORTS = ROOT / "reports"

for folder in (RAW, SILVER, REPORTS):
    folder.mkdir(parents=True, exist_ok=True)

# Approximate study-area bounds, NOT an official boundary.
SOUTH, WEST, NORTH, EAST = 10.85, 76.85, 11.15, 77.15

# Preliminary screening threshold only; not a validated standard.
REVIEW_DISTANCE_METRES = 100.0

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

walking_graph_path = RAW / f"roads_walking_osm_{timestamp}.graphml"
output_csv = SILVER / f"healthcare_network_matches_{timestamp}.csv"
report_path = REPORTS / f"healthcare_network_matches_{timestamp}.json"


def latest_file(pattern):
    files = sorted(RAW.glob(pattern))
    if not files:
        raise FileNotFoundError(
            f"No file matching {pattern} found in {RAW}"
        )
    return files[-1]


def load_healthcare():
    files = sorted(SILVER.glob("healthcare_clean_*.csv"))
    if not files:
        raise FileNotFoundError(
            "No healthcare_clean_*.csv found in data/silver"
        )

    path = files[-1]
    df = pd.read_csv(path)

    required = {"latitude", "longitude", "osm_id", "osm_type"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Healthcare CSV is missing columns: {sorted(missing)}")

    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df = df.dropna(subset=["latitude", "longitude"]).copy()

    # Keep points within our approximate study-area bounds.
    inside = (
        df["latitude"].between(SOUTH, NORTH)
        & df["longitude"].between(WEST, EAST)
    )
    df = df.loc[inside].copy()

    if df.empty:
        raise ValueError("No valid healthcare points inside the study bounds.")

    return path, df


def download_walking_graph():
    print("\nDownloading a separate walking network...")
    print("This may take several minutes; please do not run duplicates.")

    ox.settings.use_cache = True
    ox.settings.log_console = True
    ox.settings.requests_timeout = 180
    ox.settings.overpass_rate_limit = True

    graph = ox.graph_from_bbox(
        bbox=(WEST, SOUTH, EAST, NORTH),
        network_type="walk",
        simplify=True,
        retain_all=True,
        truncate_by_edge=True,
    )

    if len(graph.nodes) == 0 or len(graph.edges) == 0:
        raise ValueError("Downloaded walking graph has no nodes or edges.")

    ox.save_graphml(graph, filepath=walking_graph_path)
    return graph


def match_points(df, graph, mode):
    """Match facility points to nearest network nodes in metres."""
    projected_graph = ox.project_graph(graph)

    facilities = gpd.GeoDataFrame(
        df.copy(),
        geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
        crs="EPSG:4326",
    ).to_crs(projected_graph.graph["crs"])

    node_ids = ox.distance.nearest_nodes(
        projected_graph,
        X=facilities.geometry.x.to_numpy(),
        Y=facilities.geometry.y.to_numpy(),
    )

    node_ids = list(node_ids)
    distances = []

    for point, node_id in zip(facilities.geometry, node_ids):
        node = projected_graph.nodes[node_id]
        distance = math.hypot(
            point.x - float(node["x"]),
            point.y - float(node["y"]),
        )
        distances.append(distance)

    return node_ids, distances


def main():
    print("AURIS-X healthcare network matching")
    print(f"Study bounds: {SOUTH}, {WEST}, {NORTH}, {EAST}")

    healthcare_path, healthcare = load_healthcare()
    print(f"Healthcare source: {healthcare_path.name}")
    print(f"Valid healthcare points in bounds: {len(healthcare)}")

    driving_path = latest_file("roads_osm_*.graphml")
    print(f"Existing driving graph: {driving_path.name}")
    driving_graph = ox.load_graphml(driving_path)

    # Reuse existing driving graph; download only the walking graph.
    walking_graph = download_walking_graph()

    print("\nMatching facilities to driving nodes...")
    drive_ids, drive_distances = match_points(
        healthcare, driving_graph, "drive"
    )

    print("Matching facilities to walking nodes...")
    walk_ids, walk_distances = match_points(
        healthcare, walking_graph, "walk"
    )

    result = healthcare.drop(columns=["geometry"], errors="ignore").copy()

    result["drive_nearest_node_id"] = [str(x) for x in drive_ids]
    result["drive_snap_distance_m"] = drive_distances
    result["drive_review_over_100m"] = [
        d > REVIEW_DISTANCE_METRES for d in drive_distances
    ]

    result["walk_nearest_node_id"] = [str(x) for x in walk_ids]
    result["walk_snap_distance_m"] = walk_distances
    result["walk_review_over_100m"] = [
        d > REVIEW_DISTANCE_METRES for d in walk_distances
    ]

    result.to_csv(output_csv, index=False)

    report = {
        "project": "AURIS-X",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "healthcare_source_file": str(healthcare_path),
        "driving_graph_file": str(driving_path),
        "walking_graph_file": str(walking_graph_path),
        "output_csv": str(output_csv),
        "study_bounds": {
            "south": SOUTH,
            "west": WEST,
            "north": NORTH,
            "east": EAST,
            "official_boundary": False,
        },
        "facility_count": len(result),
        "driving_graph_nodes": len(driving_graph.nodes),
        "driving_graph_edges": len(driving_graph.edges),
        "walking_graph_nodes": len(walking_graph.nodes),
        "walking_graph_edges": len(walking_graph.edges),
        "driving_matches_over_100m": int(
            result["drive_review_over_100m"].sum()
        ),
        "walking_matches_over_100m": int(
            result["walk_review_over_100m"].sum()
        ),
        "driving_snap_distance_m": {
            "median": float(result["drive_snap_distance_m"].median()),
            "maximum": float(result["drive_snap_distance_m"].max()),
        },
        "walking_snap_distance_m": {
            "median": float(result["walk_snap_distance_m"].median()),
            "maximum": float(result["walk_snap_distance_m"].max()),
        },
        "screening_threshold_m": REVIEW_DISTANCE_METRES,
        "threshold_note": (
            "100 m is a preliminary review flag, not a validated universal "
            "standard. Review flagged points and network context."
        ),
        "limitations": [
            "Nearest-node matching is not route calculation.",
            "Snap distance is not walking or driving travel distance.",
            "A nearby node does not prove that the facility entrance connects "
            "to the network.",
            "OSM coverage and access tags may be incomplete or incorrect.",
            "Walking and driving graphs represent different permitted networks.",
            "The study bounds are approximate, not an official city boundary.",
        ],
    }

    report_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("\nSUCCESS")
    print(f"Facilities matched: {len(result)}")
    print(f"Driving matches over 100 m: {report['driving_matches_over_100m']}")
    print(f"Walking matches over 100 m: {report['walking_matches_over_100m']}")
    print(f"Matched CSV: {output_csv}")
    print(f"Report: {report_path}")
    print(f"Walking graph: {walking_graph_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nFAILED: {type(exc).__name__}: {exc}")
        sys.exit(1)
