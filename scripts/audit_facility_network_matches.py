
import json
from pathlib import Path

import networkx as nx
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)

MATCHES = DATA / "silver" / "healthcare_network_matches_20261011_122708.csv"
DRIVE = DATA / "raw" / "roads_osm_20261011_115925.graphml"
WALK = DATA / "raw" / "roads_walking_osm_20261011_122708.graphml"


def normalize_id(value):
    if pd.isna(value):
        return None
    value = str(value).strip()
    try:
        number = float(value)
        if number.is_integer():
            return str(int(number))
    except (ValueError, OverflowError):
        pass
    return value


def main():
    for path in (MATCHES, DRIVE, WALK):
        if not path.exists():
            raise FileNotFoundError(f"Required input missing: {path}")

    df = pd.read_csv(MATCHES, dtype=str).fillna("")
    drive_graph = nx.read_graphml(DRIVE)
    walk_graph = nx.read_graphml(WALK)

    required = [
        "drive_nearest_node_id",
        "walk_nearest_node_id",
        "drive_snap_distance_m",
        "walk_snap_distance_m",
    ]
    missing_columns = [c for c in required if c not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing CSV columns: {missing_columns}")

    drive_nodes = {normalize_id(n) for n in drive_graph.nodes}
    walk_nodes = {normalize_id(n) for n in walk_graph.nodes}

    df["_drive_id"] = df["drive_nearest_node_id"].map(normalize_id)
    df["_walk_id"] = df["walk_nearest_node_id"].map(normalize_id)

    df["_drive_found"] = df["_drive_id"].isin(drive_nodes)
    df["_walk_found"] = df["_walk_id"].isin(walk_nodes)

    df["_drive_snap_m"] = pd.to_numeric(
        df["drive_snap_distance_m"], errors="coerce"
    )
    df["_walk_snap_m"] = pd.to_numeric(
        df["walk_snap_distance_m"], errors="coerce"
    )

    missing_drive = df.loc[~df["_drive_found"]].copy()
    missing_walk = df.loc[~df["_walk_found"]].copy()

    missing_drive.to_csv(
        REPORTS / "audit_missing_driving_matches.csv", index=False
    )
    missing_walk.to_csv(
        REPORTS / "audit_missing_walking_matches.csv", index=False
    )

    report = {
        "input_matches": str(MATCHES.relative_to(ROOT)),
        "facility_rows": int(len(df)),
        "unique_facility_osm_ids": (
            int(df["osm_id"].nunique()) if "osm_id" in df.columns else None
        ),
        "driving_graph_nodes": int(drive_graph.number_of_nodes()),
        "driving_graph_edges": int(drive_graph.number_of_edges()),
        "walking_graph_nodes": int(walk_graph.number_of_nodes()),
        "walking_graph_edges": int(walk_graph.number_of_edges()),
        "driving_matches_found": int(df["_drive_found"].sum()),
        "driving_matches_missing": int((~df["_drive_found"]).sum()),
        "walking_matches_found": int(df["_walk_found"].sum()),
        "walking_matches_missing": int((~df["_walk_found"]).sum()),
        "unique_driving_matched_nodes": int(df["_drive_id"].nunique()),
        "unique_walking_matched_nodes": int(df["_walk_id"].nunique()),
        "driving_snap_missing_values": int(df["_drive_snap_m"].isna().sum()),
        "walking_snap_missing_values": int(df["_walk_snap_m"].isna().sum()),
        "driving_snap_over_100m": int((df["_drive_snap_m"] > 100).sum()),
        "walking_snap_over_100m": int((df["_walk_snap_m"] > 100).sum()),
        "driving_snap_max_m": (
            float(df["_drive_snap_m"].max())
            if df["_drive_snap_m"].notna().any() else None
        ),
        "walking_snap_max_m": (
            float(df["_walk_snap_m"].max())
            if df["_walk_snap_m"].notna().any() else None
        ),
        "missing_driving_report": "reports/audit_missing_driving_matches.csv",
        "missing_walking_report": "reports/audit_missing_walking_matches.csv",
        "interpretation": (
            "Node membership and snap-distance audit only. "
            "This does not validate road completeness or travel times."
        ),
    }

    output = REPORTS / "facility_network_match_audit.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n=== FACILITY NETWORK MATCH AUDIT ===")
    for key, value in report.items():
        print(f"{key}: {value}")
    print(f"\nSaved report: {output}")


if __name__ == "__main__":
    main()
