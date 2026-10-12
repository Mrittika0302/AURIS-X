
from pathlib import Path

import pandas as pd
import networkx as nx


ROOT = Path(__file__).resolve().parent.parent

FACILITIES_CSV = (
    ROOT / "data" / "silver"
    / "healthcare_network_matches_20261011_122708.csv"
)

DRIVING_GRAPH = (
    ROOT / "data" / "raw"
    / "roads_osm_20261011_115925.graphml"
)

WALKING_GRAPH = (
    ROOT / "data" / "raw"
    / "roads_walking_osm_20261011_122708.graphml"
)


def normalize_id(value):
    if pd.isna(value):
        return None
    return str(value).strip()


def audit_mode(facilities, graph_path, node_column, mode):
    print(f"\n{'=' * 60}")
    print(f"{mode.upper()} FACILITY SOURCE-NODE AUDIT")
    print(f"{'=' * 60}")

    graph = nx.read_graphml(graph_path)
    graph_nodes = {str(node) for node in graph.nodes}

    facilities = facilities.copy()
    facilities["_node"] = facilities[node_column].map(normalize_id)

    valid = facilities[
        facilities["_node"].notna()
        & facilities["_node"].isin(graph_nodes)
    ].copy()

    missing = len(facilities) - len(valid)

    print("Facility records:", len(facilities))
    print("Records with valid graph nodes:", len(valid))
    print("Records with missing/invalid graph nodes:", missing)
    print("Unique valid facility nodes:", valid["_node"].nunique())

    counts = valid.groupby("_node").size()
    shared_nodes = counts[counts > 1]

    print("Nodes shared by multiple facility records:", len(shared_nodes))
    print(
        "Facility records on shared nodes:",
        int(shared_nodes.sum()) if len(shared_nodes) else 0,
    )
    print(
        "Additional records beyond one per shared node:",
        int((shared_nodes - 1).sum()) if len(shared_nodes) else 0,
    )

    if len(shared_nodes):
        columns = [
            column for column in
            ["_node", "osm_id", "name", "category"]
            if column in valid.columns
        ]

        examples = (
            valid[valid["_node"].isin(shared_nodes.index)][columns]
            .sort_values("_node")
            .head(30)
        )

        print("\nExamples of facilities sharing a node:")
        print(examples.to_string(index=False))
    else:
        print("No shared facility nodes found.")

    return {
        "mode": mode,
        "facility_records": len(facilities),
        "valid_records": len(valid),
        "invalid_records": missing,
        "unique_valid_nodes": int(valid["_node"].nunique()),
        "shared_nodes": int(len(shared_nodes)),
        "records_on_shared_nodes": (
            int(shared_nodes.sum()) if len(shared_nodes) else 0
        ),
        "additional_records_on_shared_nodes": (
            int((shared_nodes - 1).sum())
            if len(shared_nodes) else 0
        ),
    }


def main():
    if not FACILITIES_CSV.exists():
        raise FileNotFoundError(FACILITIES_CSV)

    facilities = pd.read_csv(FACILITIES_CSV)

    print("AURIS-X facility source-node diagnostic")
    print("Read-only: existing accessibility results will not change.")

    required = [
        "osm_id",
        "name",
        "category",
        "drive_nearest_node_id",
        "walk_nearest_node_id",
    ]

    missing_columns = [
        column for column in required
        if column not in facilities.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {missing_columns}\n"
            f"Available columns: {list(facilities.columns)}"
        )

    driving = audit_mode(
        facilities,
        DRIVING_GRAPH,
        "drive_nearest_node_id",
        "driving",
    )

    walking = audit_mode(
        facilities,
        WALKING_GRAPH,
        "walk_nearest_node_id",
        "walking",
    )

    print("\nSUMMARY")
    print(pd.DataFrame([driving, walking]).to_string(index=False))
    print("\nDiagnostic complete. No existing outputs were modified.")


if __name__ == "__main__":
    main()
