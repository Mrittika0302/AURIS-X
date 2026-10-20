
import json
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx
import pandas as pd
import osmnx as ox

ROOT = Path(__file__).resolve().parent.parent
SILVER_DIR = ROOT / "data" / "silver"
RAW_DIR = ROOT / "data" / "raw"
REPORT_DIR = ROOT / "reports"

GRAPH_FILES = {
    "driving": RAW_DIR / "roads_osm_20261011_115925.graphml",
    "walking": RAW_DIR / "roads_walking_osm_20261011_122708.graphml",
}

REVIEW_SNAP_METRES = 250.0


def latest_education_csv():
    files = sorted(
        SILVER_DIR.glob("education_clean_*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError(
            "No data/silver/education_clean_*.csv file found."
        )
    return files[0]


def load_graph(path):
    if not path.exists():
        raise FileNotFoundError(f"Road graph not found: {path}")

    graph = ox.load_graphml(path)

    if not isinstance(graph, (nx.MultiDiGraph, nx.DiGraph)):
        raise TypeError(f"Unexpected graph type: {type(graph).__name__}")

    if not graph:
        raise ValueError(f"Road graph is empty: {path}")

    return graph


def match_facilities(df, graph, mode):
    valid = (
        df["latitude"].notna()
        & df["longitude"].notna()
    )

    output = df.copy()
    output[f"{mode}_node"] = pd.Series(
        [None] * len(output), index=output.index, dtype="object"
    )
    output[f"{mode}_snap_distance_m"] = float("nan")
    output[f"{mode}_match_status"] = "missing_coordinates"

    if not valid.any():
        return output

    indices = output.index[valid]
    X = pd.to_numeric(output.loc[indices, "longitude"]).to_numpy()
    Y = pd.to_numeric(output.loc[indices, "latitude"]).to_numpy()

    nearest_nodes, distances = ox.distance.nearest_nodes(
        graph,
        X=X,
        Y=Y,
        return_dist=True,
    )

    # OSMnx returns distances in metres for these projected calculations
    # when the graph is handled by its nearest-node implementation.
    for idx, node, distance in zip(indices, nearest_nodes, distances):
        output.at[idx, f"{mode}_node"] = str(node)
        output.at[idx, f"{mode}_snap_distance_m"] = float(distance)

        if node not in graph:
            output.at[idx, f"{mode}_match_status"] = "node_not_in_graph"
        elif float(distance) > REVIEW_SNAP_METRES:
            output.at[idx, f"{mode}_match_status"] = "matched_review_snap"
        else:
            output.at[idx, f"{mode}_match_status"] = "matched"

    return output


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    csv_path = latest_education_csv()
    df = pd.read_csv(csv_path)

    required = {"osm_type", "osm_id", "latitude", "longitude"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    print("=" * 60)
    print("AURIS-X EDUCATION ROAD-NETWORK MATCHING")
    print("=" * 60)
    print(f"Input: {csv_path}")
    print(f"Education records: {len(df)}")

    combined = df.copy()
    graph_summaries = {}

    for mode, graph_path in GRAPH_FILES.items():
        print(f"\nLoading {mode} graph: {graph_path.name}")
        graph = load_graph(graph_path)

        print(
            f"Graph nodes: {graph.number_of_nodes():,}; "
            f"edges: {graph.number_of_edges():,}"
        )

        combined = match_facilities(combined, graph, mode)

        status_col = f"{mode}_match_status"
        distance_col = f"{mode}_snap_distance_m"

        statuses = combined[status_col].value_counts(dropna=False).to_dict()
        distances = pd.to_numeric(
            combined[distance_col], errors="coerce"
        ).dropna()

        graph_summaries[mode] = {
            "graph_file": str(graph_path.relative_to(ROOT)),
            "node_count": graph.number_of_nodes(),
            "edge_count": graph.number_of_edges(),
            "match_status_counts": {
                str(k): int(v) for k, v in statuses.items()
            },
            "snap_distance_count": int(len(distances)),
            "snap_distance_median": (
                float(distances.median()) if len(distances) else None
            ),
            "snap_distance_max": (
                float(distances.max()) if len(distances) else None
            ),
            "snap_over_review_threshold": int(
                (distances > REVIEW_SNAP_METRES).sum()
            ),
        }

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    output_csv = (
        SILVER_DIR / f"education_network_matches_{timestamp}.csv"
    )
    output_json = (
        REPORT_DIR / f"education_network_matches_{timestamp}.json"
    )

    combined.to_csv(output_csv, index=False, encoding="utf-8-sig")

    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "input_file": str(csv_path.relative_to(ROOT)),
        "output_file": str(output_csv.relative_to(ROOT)),
        "facility_count": int(len(combined)),
        "review_snap_threshold_m": REVIEW_SNAP_METRES,
        "graph_summaries": graph_summaries,
        "limitations": [
            "Nearest-node matching is a geometric approximation.",
            "A matched node does not prove a legal or practical entrance.",
            "Snap distance is not walking or driving travel distance.",
            "Facilities outside the study-area bounding box are not automatically removed.",
            "OSM facility completeness and operating status are unverified.",
        ],
    }

    with output_json.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\nMATCHING COMPLETE")
    print(f"Input facilities: {len(df)}")
    print(f"Output CSV: {output_csv}")
    print(f"Report JSON: {output_json}")

    for mode, summary in graph_summaries.items():
        print(f"\n{mode.upper()} STATUS COUNTS")
        for status, count in summary["match_status_counts"].items():
            print(f"  {status}: {count}")
        print(
            f"Median snap distance: "
            f"{summary['snap_distance_median']} m"
        )
        print(
            f"Maximum snap distance: "
            f"{summary['snap_distance_max']} m"
        )
        print(
            f"Snaps over {REVIEW_SNAP_METRES:.0f} m: "
            f"{summary['snap_over_review_threshold']}"
        )


if __name__ == "__main__":
    main()
