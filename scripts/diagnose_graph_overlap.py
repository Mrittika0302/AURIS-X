
from pathlib import Path
import math
import networkx as nx
import numpy as np

ROOT = Path(__file__).resolve().parent.parent

FILES = {
    "driving": ROOT / "data" / "raw" / "roads_osm_20261011_115925.graphml",
    "walking": ROOT / "data" / "raw" / "roads_walking_osm_20261011_122708.graphml",
}


def edge_length_map(graph):
    """Minimum length per directed node pair, including parallel edges."""
    result = {}
    for u, v, attrs in graph.edges(data=True):
        try:
            length = float(attrs["length"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(length) and length > 0:
            key = (str(u), str(v))
            result[key] = min(result.get(key, float("inf")), length)
    return result


def main():
    graphs = {}
    for name, path in FILES.items():
        print(f"\nLoading {name}: {path.name}")
        if not path.exists():
            raise FileNotFoundError(path)
        graph = nx.read_graphml(path)
        graph = nx.relabel_nodes(
            graph, {n: str(n) for n in graph.nodes}, copy=True
        )
        graphs[name] = graph
        print("Nodes:", graph.number_of_nodes())
        print("Edges:", graph.number_of_edges())
        print("Directed:", graph.is_directed())
        print("MultiGraph:", graph.is_multigraph())

    drive = edge_length_map(graphs["driving"])
    walk = edge_length_map(graphs["walking"])

    shared = set(drive) & set(walk)
    drive_only = set(drive) - set(walk)
    walk_only = set(walk) - set(drive)

    print("\nDIRECTED NODE-PAIR COMPARISON")
    print("Driving directed pairs:", len(drive))
    print("Walking directed pairs:", len(walk))
    print("Shared pairs:", len(shared))
    print("Driving-only pairs:", len(drive_only))
    print("Walking-only pairs:", len(walk_only))

    if shared:
        differences = np.array(
            [abs(drive[k] - walk[k]) for k in shared], dtype=float
        )
        equal = differences <= 0.01
        print("\nSHARED EDGE-LENGTH COMPARISON")
        print("Lengths equal within 1 cm:", int(equal.sum()))
        print("Equal percentage:", round(float(equal.mean() * 100), 2))
        print("Median absolute length difference (m):",
              float(np.median(differences)))
        print("P90 absolute length difference (m):",
              float(np.quantile(differences, 0.90)))
        print("Maximum absolute length difference (m):",
              float(differences.max()))

        examples = sorted(
            ((abs(drive[k] - walk[k]), k, drive[k], walk[k])
             for k in shared),
            reverse=True
        )[:10]
        print("\nLARGEST SHARED-PAIR LENGTH DIFFERENCES")
        for diff, pair, dlen, wlen in examples:
            print(pair, "drive=", dlen, "walk=", wlen, "diff=", diff)

    print("\nDONE — no files changed.")


if __name__ == "__main__":
    main()
