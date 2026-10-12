
from pathlib import Path
import json
import networkx as nx
import osmnx as ox

ROOT = Path(__file__).resolve().parents[1]

DRIVE_FILE = (
    ROOT / "data" / "raw" /
    "roads_osm_20261011_115925.graphml"
)
WALK_FILE = (
    ROOT / "data" / "raw" /
    "roads_walking_osm_20261011_122708.graphml"
)

# Largest discrepancies and one pair with a higher length ratio.
TARGET_PAIRS = [
    ("6965421644", "6965421653"),
    ("9068977797", "9068977796"),
    ("5655107628", "9676768874"),
    ("13999738633", "13999738634"),
    ("5668292289", "5668292290"),
]


def load_graph(path):
    graph = ox.load_graphml(path)
    return nx.relabel_nodes(
        graph,
        {node: str(node) for node in graph.nodes},
        copy=True,
    )


def describe_node(graph, node_id):
    if node_id not in graph:
        print(f"  Node {node_id}: NOT PRESENT")
        return

    node = graph.nodes[node_id]
    print(
        f"  Node {node_id}: "
        f"lon={node.get('x')}, lat={node.get('y')}"
    )


def inspect_pair(graph, label, u, v):
    print(f"\n  {label}: {u} -> {v}")

    if not graph.has_edge(u, v):
        print("    No directed edge.")
    else:
        for key, attrs in graph.get_edge_data(u, v).items():
            selected = {
                k: attrs.get(k)
                for k in (
                    "length", "osmid", "highway", "name",
                    "oneway", "reversed", "access", "foot",
                    "motor_vehicle", "geometry"
                )
                if k in attrs
            }

            # Geometry can be long; report whether it exists
            # and how many coordinates it contains.
            geometry = selected.pop("geometry", None)
            if geometry is not None:
                selected["geometry_present"] = True
                try:
                    selected["geometry_coordinate_count"] = len(
                        geometry.coords
                    )
                except (AttributeError, TypeError):
                    selected["geometry_coordinate_count"] = None
            else:
                selected["geometry_present"] = False

            print(f"    Edge key={key}:")
            print("    " + json.dumps(selected, default=str))

    if graph.has_edge(v, u):
        print(f"    Reverse direction {v} -> {u}:")
        for key, attrs in graph.get_edge_data(v, u).items():
            print(
                "      "
                + json.dumps(
                    {
                        "key": key,
                        "length": attrs.get("length"),
                        "osmid": attrs.get("osmid"),
                        "highway": attrs.get("highway"),
                        "name": attrs.get("name"),
                        "oneway": attrs.get("oneway"),
                    },
                    default=str,
                )
            )
    else:
        print(f"    No reverse edge {v} -> {u}.")


def inspect_neighbours(graph, label, node_id):
    print(f"\n  {label} neighbours of {node_id}:")

    if node_id not in graph:
        print("    Node missing.")
        return

    # Combine predecessors and successors without duplicates.
    neighbours = sorted(
        set(graph.predecessors(node_id))
        | set(graph.successors(node_id))
    )

    print(f"    Unique adjacent nodes: {len(neighbours)}")

    for other in neighbours:
        for u, v in ((node_id, other), (other, node_id)):
            if not graph.has_edge(u, v):
                continue

            for key, attrs in graph.get_edge_data(u, v).items():
                print(
                    "    "
                    f"{u} -> {v}, key={key}, "
                    f"length={attrs.get('length')}, "
                    f"highway={attrs.get('highway')}, "
                    f"osmid={attrs.get('osmid')}"
                )


def main():
    print("Loading existing graphs; no downloads required.")
    drive = load_graph(DRIVE_FILE)
    walk = load_graph(WALK_FILE)

    for u, v in TARGET_PAIRS:
        print("\n" + "=" * 75)
        print(f"TARGET PAIR: {u} -> {v}")

        describe_node(drive, u)
        describe_node(drive, v)

        inspect_pair(drive, "DRIVING", u, v)
        inspect_pair(walk, "WALKING", u, v)

        inspect_neighbours(walk, "WALKING", u)
        inspect_neighbours(walk, "WALKING", v)

    print("\n" + "=" * 75)
    print("Inspection complete. No files modified.")


if __name__ == "__main__":
    main()
