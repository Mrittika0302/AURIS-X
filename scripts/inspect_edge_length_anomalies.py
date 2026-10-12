
from pathlib import Path
import networkx as nx
import osmnx as ox
import json

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


def pair_lengths(graph):
    result = {}

    for u, v, key, data in graph.edges(keys=True, data=True):
        length = float(data["length"])
        pair = (str(u), str(v))

        # Match the earlier diagnostic's minimum-length comparison
        # for each directed node pair.
        if pair not in result or length < result[pair]:
            result[pair] = length

    return result


def main():
    print("Loading graphs...")
    drive = load_graph(DRIVE_FILE)
    walk = load_graph(WALK_FILE)

    drive_lengths = pair_lengths(drive)
    walk_lengths = pair_lengths(walk)

    differences = []

    for pair in drive_lengths.keys() & walk_lengths.keys():
        d = drive_lengths[pair]
        w = walk_lengths[pair]
        delta = abs(d - w)

        if delta > 0.01:
            differences.append((delta, pair, d, w))

    differences.sort(reverse=True)

    print(f"\nShared directed pairs differing by > 1 cm: {len(differences)}")
    print("\nLargest discrepancies and underlying edge attributes:")

    for delta, (u, v), d, w in differences[:10]:
        print("\n" + "-" * 65)
        print(f"Directed pair: {u} -> {v}")
        print(f"Driving minimum length: {d:.3f} m")
        print(f"Walking minimum length: {w:.3f} m")
        print(f"Absolute difference: {delta:.3f} m")

        for label, graph in (("DRIVING", drive), ("WALKING", walk)):
            print(f"\n{label} edge records:")
            if not graph.has_edge(u, v):
                print("No edge for this direction.")
                continue

            edge_data = graph.get_edge_data(u, v)

            for key, attrs in edge_data.items():
                # Print tags that help explain route/network differences.
                selected = {
                    name: attrs.get(name)
                    for name in (
                        "length",
                        "highway",
                        "name",
                        "oneway",
                        "reversed",
                        "osmid",
                        "access",
                        "foot",
                        "motor_vehicle",
                        "bridge",
                        "tunnel",
                    )
                    if name in attrs
                }
                print("key =", key)
                print(json.dumps(selected, default=str))

    print("\nInspection complete. No files modified.")


if __name__ == "__main__":
    main()
