
import math
import networkx as nx

GRAPHS = {
    "driving": "data/raw/roads_osm_20261011_115925.graphml",
    "walking": "data/raw/roads_walking_osm_20261011_122708.graphml",
}

graphs = {}

for name, path in GRAPHS.items():
    print(f"\n{'=' * 60}")
    print(f"Checking {name} graph")
    print(f"File: {path}")

    G = nx.read_graphml(path)
    graphs[name] = G

    lengths = []
    invalid_lengths = 0

    for _, _, _, data in G.edges(keys=True, data=True):
        try:
            length = float(data["length"])
            if math.isfinite(length) and length > 0:
                lengths.append(length)
            else:
                invalid_lengths += 1
        except (KeyError, TypeError, ValueError):
            invalid_lengths += 1

    lengths.sort()

    print("Graph type:", type(G).__name__)
    print("Nodes:", G.number_of_nodes())
    print("Edges:", G.number_of_edges())
    print("Valid positive edge lengths:", len(lengths))
    print("Invalid edge lengths:", invalid_lengths)

    if lengths:
        print("Minimum edge length (m):", round(lengths[0], 2))
        print("Median edge length (m):", round(lengths[len(lengths) // 2], 2))
        print("Maximum edge length (m):", round(lengths[-1], 2))

    print("CRS:", G.graph.get("crs"))

driving = graphs["driving"]
walking = graphs["walking"]

# Compare directed connections, ignoring parallel-edge keys.
drive_pairs = set(driving.edges())
walk_pairs = set(walking.edges())

print(f"\n{'=' * 60}")
print("DRIVING VS WALKING COMPARISON")
print("Shared directed node pairs:", len(drive_pairs & walk_pairs))
print("Driving-only directed pairs:", len(drive_pairs - walk_pairs))
print("Walking-only directed pairs:", len(walk_pairs - drive_pairs))
print("Shared nodes:", len(set(driving.nodes()) & set(walking.nodes())))

print("\nDiagnostic complete. No files were modified.")
