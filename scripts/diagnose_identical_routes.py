
from pathlib import Path
import pandas as pd
import networkx as nx

ROOT = Path(__file__).resolve().parent.parent

ACCESS = ROOT / "data" / "gold" / "healthcare_accessibility_by_population_cell.csv"
DRIVE_GRAPH = ROOT / "data" / "raw" / "roads_osm_20261011_115925.graphml"
WALK_GRAPH = ROOT / "data" / "raw" / "roads_walking_osm_20261011_122708.graphml"


def node_text(value):
    return None if pd.isna(value) else str(value).strip()


def main():
    df = pd.read_csv(ACCESS)

    drive = pd.to_numeric(df["driving_distance_m"], errors="coerce")
    walk = pd.to_numeric(df["walking_distance_m"], errors="coerce")
    both = drive.notna() & walk.notna()

    identical = df.loc[both & ((drive - walk).abs() < 0.001)].copy()
    different = df.loc[both & ((drive - walk).abs() > 1000)].copy()

    print("Identical distances:", len(identical))
    print("Differences over 1 km:", len(different))

    print("\nIDENTICAL DISTANCES — NODE MATCHING")
    print("Population drive node equals walk node:",
          int((identical["drive_nearest_node_id"].astype(str)
               == identical["walk_nearest_node_id"].astype(str)).sum()))
    print("Facility IDs equal:",
          int((identical["driving_facility_id"].astype(str)
               == identical["walking_facility_id"].astype(str)).sum()))

    print("\nLARGEST DIFFERENCES — NODE MATCHING")
    different["_delta_m"] = (
        pd.to_numeric(different["driving_distance_m"])
        - pd.to_numeric(different["walking_distance_m"])
    ).abs()
    cols = [
        "population_cell_id",
        "drive_nearest_node_id", "walk_nearest_node_id",
        "driving_facility_id", "walking_facility_id",
        "driving_distance_m", "walking_distance_m", "_delta_m",
    ]
    print(different.nlargest(10, "_delta_m")[cols].to_string(index=False))

    print("\nLoading graphs to check node presence...")
    dg = nx.read_graphml(DRIVE_GRAPH)
    wg = nx.read_graphml(WALK_GRAPH)
    drive_nodes = {str(n) for n in dg.nodes}
    walk_nodes = {str(n) for n in wg.nodes}

    for label, sample in [
        ("IDENTICAL", identical.head(100)),
        ("LARGE DIFFERENCE", different.nlargest(100, "_delta_m")),
    ]:
        pop_drive = sample["drive_nearest_node_id"].map(node_text)
        pop_walk = sample["walk_nearest_node_id"].map(node_text)
        fac_drive = sample["driving_facility_id"].map(node_text)
        fac_walk = sample["walking_facility_id"].map(node_text)

        print(f"\n{label} SAMPLE — {len(sample)} rows")
        print("Population drive nodes present:", int(pop_drive.isin(drive_nodes).sum()))
        print("Population walk nodes present:", int(pop_walk.isin(walk_nodes).sum()))
        print("Facility IDs are OSM facility IDs, not graph nodes.")
        print("This test confirms population node presence only.")
        print("Facility node checks require joining the facility matching CSV.")

    print("\nDONE — no files changed.")


if __name__ == "__main__":
    main()
