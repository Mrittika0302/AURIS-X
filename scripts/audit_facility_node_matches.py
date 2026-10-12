
from pathlib import Path
import glob
import json
import os

import pandas as pd
import osmnx as ox

ROOT = Path(__file__).resolve().parent.parent


def latest(pattern):
    files = glob.glob(str(ROOT / pattern))
    if not files:
        raise FileNotFoundError(f"No files found for: {pattern}")
    return Path(max(files, key=os.path.getmtime))


def normalize_node_id(value):
    """Normalize integer-like IDs read from CSV without altering real IDs."""
    if pd.isna(value):
        return None
    text = str(value).strip()
    try:
        number = float(text)
        if number.is_integer():
            return str(int(number))
    except ValueError:
        pass
    return text


def audit_mode(matches, graph, node_column, mode):
    graph_ids = {str(node) for node in graph.nodes}
    normalized = matches[node_column].map(normalize_node_id)

    missing_mask = ~normalized.isin(graph_ids)
    missing = matches.loc[missing_mask].copy()

    result = {
        "mode": mode,
        "facility_rows": int(len(matches)),
        "matched_node_ids_found": int((~missing_mask).sum()),
        "matched_node_ids_missing": int(missing_mask.sum()),
        "missing_examples": [],
    }

    for _, row in missing.head(15).iterrows():
        result["missing_examples"].append({
            "osm_type": str(row["osm_type"]),
            "osm_id": normalize_node_id(row["osm_id"]),
            "name": None if pd.isna(row["name"]) else str(row["name"]),
            "category": str(row["category"]),
            "matched_graph_node_id": normalize_node_id(row[node_column]),
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
        })

    return result


def main():
    matches_path = latest(
        "data/silver/healthcare_network_matches_*.csv"
    )
    drive_path = latest("data/raw/roads_osm_*.graphml")
    walk_path = latest("data/raw/roads_walking_osm_*.graphml")

    matches = pd.read_csv(matches_path)
    drive_graph = ox.load_graphml(drive_path)
    walk_graph = ox.load_graphml(walk_path)

    # Check graph IDs using normalized IDs to avoid CSV float-format issues.
    drive_ids = {str(node) for node in drive_graph.nodes}
    walk_ids = {str(node) for node in walk_graph.nodes}

    drive_normalized = matches["drive_nearest_node_id"].map(
        normalize_node_id
    )
    walk_normalized = matches["walk_nearest_node_id"].map(
        normalize_node_id
    )

    report = {
        "matches_file": str(matches_path),
        "driving_graph_file": str(drive_path),
        "walking_graph_file": str(walk_path),
        "driving": audit_mode(
            matches, drive_graph, "drive_nearest_node_id", "driving"
        ),
        "walking": audit_mode(
            matches, walk_graph, "walk_nearest_node_id", "walking"
        ),
        "cross_network_checks": {
            "driving_matched_ids_found_in_walking_graph": int(
                drive_normalized.isin(walk_ids).sum()
            ),
            "walking_matched_ids_found_in_driving_graph": int(
                walk_normalized.isin(drive_ids).sum()
            ),
        },
        "important_note": (
            "This checks whether matched node IDs exist in each graph. "
            "It does not prove the facility is reachable or that the "
            "network adequately represents real-world access."
        ),
    }

    output = ROOT / "reports" / "facility_node_match_audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("FACILITY NODE MATCH AUDIT COMPLETE")
    print(json.dumps(report, indent=2))
    print(f"\nReport saved to: {output}")


if __name__ == "__main__":
    main()
