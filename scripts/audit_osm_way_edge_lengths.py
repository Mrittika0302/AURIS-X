
from pathlib import Path
from collections import defaultdict
import networkx as nx
import osmnx as ox
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

FILES = {
    "drive": ROOT / "data" / "raw" / "roads_osm_20261011_115925.graphml",
    "walk": ROOT / "data" / "raw" / "roads_walking_osm_20261011_122708.graphml",
}

OUTPUT = ROOT / "reports" / "osm_way_edge_length_audit.csv"


def load_graph(path):
    graph = ox.load_graphml(path)
    return nx.relabel_nodes(
        graph, {n: str(n) for n in graph.nodes}, copy=True
    )


def osmids(value):
    if isinstance(value, (list, tuple, set)):
        return [str(x) for x in value]
    if value is None:
        return []
    return [str(value)]


def collect(graph, mode):
    records = []

    for u, v, key, data in graph.edges(keys=True, data=True):
        ids = osmids(data.get("osmid"))

        for osmid in ids:
            records.append({
                "mode": mode,
                "u": str(u),
                "v": str(v),
                "key": str(key),
                "osmid": osmid,
                "length_m": float(data["length"]),
                "highway": str(data.get("highway")),
                "name": str(data.get("name")),
                "geometry_present": data.get("geometry") is not None,
            })

    return records


def main():
    records = []

    for mode, path in FILES.items():
        print(f"Loading {mode}: {path.name}")
        graph = load_graph(path)
        records.extend(collect(graph, mode))

    edges = pd.DataFrame(records)

    # Compare each OSM way's edge-length distribution in both graphs.
    summary = (
        edges.groupby(["mode", "osmid"])
        .agg(
            edge_records=("length_m", "size"),
            total_recorded_length_m=("length_m", "sum"),
            min_edge_length_m=("length_m", "min"),
            max_edge_length_m=("length_m", "max"),
            highway_values=("highway", lambda s: ";".join(sorted(set(s)))),
            names=("name", lambda s: ";".join(sorted(set(s)))),
            geometry_missing_records=(
                "geometry_present", lambda s: int((~s).sum())
            ),
        )
        .reset_index()
    )

    wide = summary.pivot(
        index="osmid",
        columns="mode",
        values=[
            "edge_records",
            "total_recorded_length_m",
            "min_edge_length_m",
            "max_edge_length_m",
        ],
    )

    wide.columns = [
        f"{metric}_{mode}" for metric, mode in wide.columns
    ]
    wide = wide.reset_index()

    for col in [
        "edge_records_drive", "edge_records_walk",
        "total_recorded_length_m_drive",
        "total_recorded_length_m_walk",
        "min_edge_length_m_drive", "min_edge_length_m_walk",
        "max_edge_length_m_drive", "max_edge_length_m_walk",
    ]:
        if col not in wide.columns:
            wide[col] = pd.NA

    wide["total_length_difference_m"] = (
        wide["total_recorded_length_m_drive"]
        - wide["total_recorded_length_m_walk"]
    ).abs()

    wide["edge_count_difference"] = (
        wide["edge_records_drive"] - wide["edge_records_walk"]
    ).abs()

    wide["present_in_both"] = (
        wide["edge_records_drive"].notna()
        & wide["edge_records_walk"].notna()
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    wide.to_csv(OUTPUT, index=False)

    print("\nAudit complete.")
    print("Unique OSM way IDs:", len(wide))
    print("Present in both graphs:", int(wide["present_in_both"].sum()))
    print("Output:", OUTPUT)

    common = wide[wide["present_in_both"]].copy()
    common = common.sort_values(
        "total_length_difference_m", ascending=False
    )

    print("\nLargest total recorded-length differences for shared OSM IDs:")
    print(common.head(20).to_string(index=False))

    print(
        "\nNote: total_recorded_length_m sums edge records, including "
        "opposite directions and repeated OSM IDs on simplified edges. "
        "It is a diagnostic comparison, not a physical road-length estimate."
    )


if __name__ == "__main__":
    main()
