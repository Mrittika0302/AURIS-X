
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

ACCESS_FILE = (
    ROOT
    / "data"
    / "gold"
    / "healthcare_accessibility_by_population_cell.csv"
)

FACILITY_FILE = (
    ROOT
    / "data"
    / "silver"
    / "healthcare_network_matches_20261011_122708.csv"
)


def normalize_id(series):
    """Normalize OSM IDs and graph-node IDs for comparison."""
    return (
        series.astype("string")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )


def audit_mode(access, facilities, mode):
    print("\n" + "=" * 68)
    print(f"{mode.upper()} FACILITY-TO-NODE ASSIGNMENT AUDIT")
    print("=" * 68)

    if mode == "driving":
        facility_node_col = "drive_nearest_node_id"
        assigned_id_col = "driving_facility_id"
        distance_col = "driving_distance_m"
    else:
        facility_node_col = "walk_nearest_node_id"
        assigned_id_col = "walking_facility_id"
        distance_col = "walking_distance_m"

    source = facilities[
        ["osm_id", facility_node_col, "name", "category"]
    ].copy()

    source["osm_id_norm"] = normalize_id(source["osm_id"])
    source["node_norm"] = normalize_id(source[facility_node_col])

    # Count how many source records share each snapped node.
    node_counts = source.groupby("node_norm", dropna=False).size()
    shared_nodes = node_counts[node_counts > 1]

    print(f"Facility source records: {len(source):,}")
    print(f"Unique non-missing snapped nodes: {source['node_norm'].nunique():,}")
    print(f"Nodes shared by multiple facility records: {len(shared_nodes):,}")
    print(
        "Facility records located on shared nodes: "
        f"{int(source['node_norm'].isin(shared_nodes.index).sum()):,}"
    )

    # Build a lookup by facility OSM ID.
    # Source IDs should be unique, but validate that assumption.
    duplicate_ids = source["osm_id_norm"].duplicated(keep=False)
    if duplicate_ids.any():
        print("WARNING: duplicate OSM IDs found in facility source:")
        print(
            source.loc[
                duplicate_ids,
                ["osm_id_norm", "node_norm", "name", "category"],
            ].to_string(index=False)
        )

    source_by_id = source.drop_duplicates(
        subset=["osm_id_norm"],
        keep=False,
    ).set_index("osm_id_norm")

    rows = access.loc[
        access[assigned_id_col].notna()
        & access[distance_col].notna(),
        ["population_cell_id", assigned_id_col, distance_col],
    ].copy()

    rows["assigned_id_norm"] = normalize_id(rows[assigned_id_col])

    rows = rows.join(
        source_by_id[
            ["node_norm", "name", "category"]
        ],
        on="assigned_id_norm",
    )

    rows["source_id_found"] = rows["node_norm"].notna()

    print(f"Reachable population rows audited: {len(rows):,}")
    print(
        "Rows whose assigned facility maps to a source node: "
        f"{int(rows['source_id_found'].sum()):,}"
    )
    print(
        "Rows whose assigned facility has no unique source-node mapping: "
        f"{int((~rows['source_id_found']).sum()):,}"
    )

    # Check all facility records sharing the selected node.
    shared_row_mask = rows["node_norm"].isin(shared_nodes.index)
    print(
        "Assignments selecting a node shared by multiple facilities: "
        f"{int(shared_row_mask.sum()):,}"
    )

    print("\nSample assignments on shared nodes:")
    sample = rows.loc[
        shared_row_mask,
        [
            "population_cell_id",
            "assigned_id_norm",
            "node_norm",
            distance_col,
            "name",
            "category",
        ],
    ].head(15)

    if sample.empty:
        print("No shared-node assignments found in this sample.")
    else:
        print(sample.to_string(index=False))

    # For shared nodes, list the complete source records so the assigned
    # facility can be compared with its co-located records.
    if not shared_nodes.empty:
        print("\nExamples of facilities sharing the same snapped node:")
        example_nodes = list(shared_nodes.index[:10])

        examples = source.loc[
            source["node_norm"].isin(example_nodes),
            ["node_norm", "osm_id_norm", "name", "category"],
        ].sort_values(["node_norm", "osm_id_norm"])

        print(examples.to_string(index=False))

    print(
        "\nInterpretation: a shared node is not automatically an error. "
        "Facilities snapped to the same node have the same network "
        "distance to that node. This audit checks metadata association; "
        "it does not independently recalculate shortest paths."
    )


def main():
    print("AURIS-X Facility-to-Node Assignment Audit")
    print("READ-ONLY: no files will be written or overwritten.\n")

    for path in (ACCESS_FILE, FACILITY_FILE):
        if not path.exists():
            raise FileNotFoundError(f"Required file not found: {path}")

    access = pd.read_csv(ACCESS_FILE)
    facilities = pd.read_csv(
        FACILITY_FILE,
        dtype={"osm_id": "string"},
    )

    required_access = [
        "population_cell_id",
        "driving_facility_id",
        "driving_distance_m",
        "walking_facility_id",
        "walking_distance_m",
    ]
    missing_access = [
        col for col in required_access if col not in access.columns
    ]
    if missing_access:
        raise ValueError(
            f"Accessibility file missing columns: {missing_access}"
        )

    required_facilities = [
        "osm_id",
        "name",
        "category",
        "drive_nearest_node_id",
        "walk_nearest_node_id",
    ]
    missing_facilities = [
        col for col in required_facilities if col not in facilities.columns
    ]
    if missing_facilities:
        raise ValueError(
            f"Facility file missing columns: {missing_facilities}"
        )

    audit_mode(access, facilities, "driving")
    audit_mode(access, facilities, "walking")

    print("\nAudit complete. Existing project outputs remain unchanged.")


if __name__ == "__main__":
    main()
