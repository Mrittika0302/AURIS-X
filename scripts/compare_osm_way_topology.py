
from pathlib import Path
from collections import defaultdict
import osmnx as ox

ROOT = Path(__file__).resolve().parents[1]

FILES = {
    "DRIVING": ROOT / "data" / "raw" / "roads_osm_20261011_115925.graphml",
    "WALKING": ROOT / "data" / "raw" / "roads_walking_osm_20261011_122708.graphml",
}

TARGET_OSMID = "1262117427"


def as_list(value):
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def get_edges(graph):
    result = []

    for u, v, key, data in graph.edges(keys=True, data=True):
        ids = {str(x) for x in as_list(data.get("osmid"))}

        if TARGET_OSMID in ids:
            result.append({
                "u": str(u),
                "v": str(v),
                "length": float(data["length"]),
                "key": str(key),
                "osmid": ids,
            })

    return result


def main():
    edge_sets = {}

    for mode, path in FILES.items():
        graph = ox.load_graphml(path)
        edges = get_edges(graph)
        edge_sets[mode] = edges

        directed_pairs = {(e["u"], e["v"]) for e in edges}
        undirected_pairs = {
            tuple(sorted((e["u"], e["v"]))) for e in edges
        }

        print(f"\n{mode}")
        print(f"  Edge records: {len(edges)}")
        print(f"  Directed endpoint pairs: {len(directed_pairs)}")
        print(f"  Undirected endpoint pairs: {len(undirected_pairs)}")
        print(
            f"  Total recorded edge length: "
            f"{sum(e['length'] for e in edges):.2f} m"
        )

    drive_directed = {
        (e["u"], e["v"]) for e in edge_sets["DRIVING"]
    }
    walk_directed = {
        (e["u"], e["v"]) for e in edge_sets["WALKING"]
    }

        drive_undirected = {
        tuple(sorted((e["u"], e["v"])))
        for e in edge_summary["drive_edges"]
    }

    walk_undirected = {
        tuple(sorted((e["u"], e["v"])))
        for e in edge_summary["walk_edges"]
    }

    print("\nCROSS-GRAPH COMPARISON")
    print("  Shared directed pairs:", len(drive_directed & walk_directed))
    print("  Driving-only directed pairs:", len(drive_directed - walk_directed))
    print("  Walking-only directed pairs:", len(walk_directed - drive_directed))
    print("  Shared undirected pairs:", len(drive_undirected & walk_undirected))
    print("  Driving-only undirected pairs:", len(drive_undirected - walk_undirected))
    print("  Walking-only undirected pairs:", len(walk_undirected - drive_undirected))

    print("\nExamples of walking-only undirected endpoint pairs:")
    for u, v in sorted(walk_undirected - drive_undirected)[:15]:
        print(f"  {u} <-> {v}")


if