
from pathlib import Path
import networkx as nx
import osmnx as ox
import pandas as pd
import math

ROOT = Path(__file__).resolve().parents[1]
DRIVE_FILE = ROOT / "data" / "raw" / "roads_osm_20261011_115925.graphml"
WALK_FILE = ROOT / "data" / "raw" / "roads_walking_osm_20261011_122708.graphml"


def load_graph(path):
    graph = ox.load_graphml(path)
    return nx.relabel_nodes(
        graph,
        {node: str(node) for node in graph.nodes},
        copy=True,
    )


def min_pair_lengths(graph):
    result = {}
    for u, v, key, data in graph.edges(keys=True, data=True):
        pair = (str(u), str(v))
        length = float(data["length"])
        if pair not in result or length < result[pair]:
            result[pair] = length
    return result


def haversine_m(lon1, lat1, lon2, lat2):
    radius = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = (
        math.sin(dp / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


def main():
    drive = load_graph(DRIVE_FILE)
    walk = load_graph(WALK_FILE)

    dmin = min_pair_lengths(drive)
    wmin = min_pair_lengths(walk)

    anomalies = sorted(
        (
            abs(dmin[pair] - wmin[pair]),
            pair,
            dmin[pair],
            wmin[pair],
        )
        for pair in dmin.keys() & wmin.keys()
        if abs(dmin[pair] - wmin[pair]) > 0.01
    )
    anomalies.sort(reverse=True)

    rows = []

    print("Inspecting all shared pairs with length differences > 1 cm.")
    print("No graph or accessibility files will be modified.")

    for delta, (u, v), drive_min, walk_min in anomalies:
        # Find the walking edge with the minimum length.
        records = walk.get_edge_data(u, v)
        short_edges = [
            (key, data)
            for key, data in records.items()
            if abs(float(data["length"]) - walk_min) <= 0.01
        ]

        udata, vdata = walk.nodes[u], walk.nodes[v]
        straight = haversine_m(
            float(udata["x"]), float(udata["y"]),
            float(vdata["x"]), float(vdata["y"]),
        )

        for key, data in short_edges:
            geometry = data.get("geometry")
            rows.append({
                "u": u,
                "v": v,
                "length_difference_m": delta,
                "drive_min_m": drive_min,
                "walk_min_m": walk_min,
                "short_edge_key": key,
                "short_edge_osmid": str(data.get("osmid")),
                "short_edge_highway": str(data.get("highway")),
                "short_edge_name": str(data.get("name")),
                "has_geometry": geometry is not None,
                "endpoint_straight_distance_m": straight,
                "length_to_straight_ratio": (
                    walk_min / straight if straight > 0 else None
                ),
            })

    out = pd.DataFrame(rows)
    output_path = ROOT / "reports" / "parallel_edge_anomaly_audit.csv"
    out.to_csv(output_path, index=False)

    print(f"\nShared directed pairs with discrepancies: {len(anomalies)}")
    print(f"Short-edge records inspected: {len(out)}")
    print(f"Missing geometry: {(~out['has_geometry']).sum()}")
    print(f"Audit CSV: {output_path}")

    print("\nLargest discrepancies:")
    if not out.empty:
        print(
            out.sort_values("length_difference_m", ascending=False)
            .head(15)
            .to_string(index=False)
        )

    print("\nDone. Original graphs and accessibility outputs unchanged.")


if __name__ == "__main__":
    main()
