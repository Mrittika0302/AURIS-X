
from pathlib import Path
import pandas as pd
import networkx as nx

ROOT = Path(__file__).resolve().parent.parent

FACILITIES = ROOT / "data" / "silver" / "healthcare_network_matches_20261011_122708.csv"
ACCESS = ROOT / "data" / "gold" / "healthcare_accessibility_by_population_cell.csv"
DRIVE_GRAPH = ROOT / "data" / "raw" / "roads_osm_20261011_115925.graphml"
WALK_GRAPH = ROOT / "data" / "raw" / "roads_walking_osm_20261011_122708.graphml"


def norm(value):
    if pd.isna(value):
        return None
    return str(value).strip()


def main():
    facilities = pd.read_csv(FACILITIES, dtype={"osm_id": str})
    access = pd.read_csv(ACCESS)

    required = [
        "osm_id",
        "drive_nearest_node_id",
        "walk_nearest_node_id",
    ]
    missing = [c for c in required if c not in facilities.columns]
    if missing:
        raise ValueError(f"Missing facility columns: {missing}")

    facilities["_id"] = facilities["osm_id"].map(norm)
    facilities["_drive_node"] = facilities["drive_nearest_node_id"].map(norm)
    facilities["_walk_node"] = facilities["walk_nearest_node_id"].map(norm)

    print("Facility rows:", len(facilities))
    print("Unique OSM IDs:", facilities["_id"].nunique())
    print("Duplicate OSM IDs:", int(facilities["_id"].duplicated().sum()))

    print("\nLoading graph node IDs...")
    dg = nx.read_graphml(DRIVE_GRAPH)
    wg = nx.read_graphml(WALK_GRAPH)
    drive_nodes = {str(n) for n in dg.nodes}
    walk_nodes = {str(n) for n in wg.nodes}

    print("\nFACILITY MATCH VALIDITY")
    print("Driving facility nodes in driving graph:",
          int(facilities["_drive_node"].isin(drive_nodes).sum()), "/", len(facilities))
    print("Walking facility nodes in walking graph:",
          int(facilities["_walk_node"].isin(walk_nodes).sum()), "/", len(facilities))

    drive_lookup = facilities.drop_duplicates("_id").set_index("_id")["_drive_node"]
    walk_lookup = facilities.drop_duplicates("_id").set_index("_id")["_walk_node"]

    for mode in ["driving", "walking"]:
        id_col = f"{mode}_facility_id"
        node_col = "_drive_node" if mode == "driving" else "_walk_node"
        graph_nodes = drive_nodes if mode == "driving" else walk_nodes

        result_ids = access[id_col].map(norm)
        expected_nodes = result_ids.map(
            drive_lookup if mode == "driving" else walk_lookup
        )

        reachable = pd.to_numeric(
            access[f"{mode}_distance_m"], errors="coerce"
        ).notna()

        print(f"\n{mode.upper()} RESULT CHECK")
        print("Reachable rows:", int(reachable.sum()))
        print("Reachable rows with facility ID found in input:",
              int((reachable & expected_nodes.notna()).sum()))
        print("Reachable rows whose mapped facility node exists in graph:",
              int((reachable & expected_nodes.isin(graph_nodes)).sum()))

        # Multiple records may share a snapped node. This check tests the
        # facility ID's own node, not whether its route is the nearest route.
        mismatches = reachable & expected_nodes.notna() & (
            expected_nodes != access[
                "drive_nearest_node_id" if mode == "driving"
                else "walk_nearest_node_id"
            ].map(norm)
        )
        print("Rows where facility node equals population node:",
              int((reachable & expected_nodes.notna() & (
                  expected_nodes == access[
                      "drive_nearest_node_id" if mode == "driving"
                      else "walk_nearest_node_id"
                  ].map(norm)
              )).sum()))
        print("Rows with different population/facility nodes:",
              int(mismatches.sum()))

        if mismatches.any():
            print("Examples:")
            cols = [
                "population_cell_id",
                id_col,
                "driving_distance_m" if mode == "driving" else "walking_distance_m",
            ]
            sample = access.loc[mismatches, cols].head(10).copy()
            sample["mapped_facility_node"] = expected_nodes[mismatches].head(10).values
            print(sample.to_string(index=False))

    print("\nDONE — no files changed.")


if __name__ == "__main__":
    main()
