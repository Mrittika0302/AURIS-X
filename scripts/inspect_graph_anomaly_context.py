
from pathlib import Path
import networkx as nx
import osmnx as ox
import json

ROOT = Path(__file__).resolve().parents[1]

DRIVE_FILE = ROOT / "data" / "raw" / "roads_osm_20261011_115925.graphml"
WALK_FILE = ROOT / "data" / "raw" / "roads_walking_osm_20261011_122708.graphml"

PAIRS = [
    ("6965421644", "6965421653"),
    ("9068977797", "9068977796"),
    ("5655107628", "9676768874"),
]


def load_graph(path):
    graph = ox.load_graphml(path)
    graph = nx.relabel_nodes(
        graph,
        {node: str(node) for node in graph.nodes},
        copy=True,
    )
    return graph


def show_node(graph, node_id):
    if node_id not in graph:
        print(f"  Node {node_id}: NOT PRESENT")
        return

    node = graph.nodes[node_id]
    print(
        f"  Node {node_id}: "
        f"x={node.get('x')}, y={node.get('y')}"
    )


def show_graph_metadata(label, graph):
    print(f"\n{'=' * 60}")
    print(label)
    print(f"Nodes: {len(graph.nodes)}")
    print(f"Edges: {len(graph.edges)}")
    print("Graph metadata:")
    print(json.dumps(graph.graph, indent=2, default=str))


def show_pair(drive, walk, u, v):
    print(f"\n{'-' * 60}")
    print(f"Directed pair: {u} -> {v}")

    for label, graph in (("DRIVING", drive), ("WALKING", walk)):
        print(f"\n{label}")
        show_node(graph, u)
        show_node(graph, v)

        if not graph.has_edge(u, v):
            print("  No directed edge.")
            continue

        for key, attrs in graph.get_edge_data(u, v).items():
            print(
                f"  Edge key={key}: "
                + json.dumps(attrs, default=str)
            )


def main():
    drive = load_graph(DRIVE_FILE)
    walk = load_graph(WALK_FILE)

    show_graph_metadata("DRIVING GRAPH", drive)
    show_graph_metadata("WALKING GRAPH", walk)

    print("\n\nANOMALOUS PAIR CONTEXT")

    for u, v in PAIRS:
        show_pair(drive, walk, u, v)

    print("\n\nInspection complete. No files modified.")


if __name__ == "__main__":
    main()
