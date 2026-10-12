
from pathlib import Path
import networkx as nx
import osmnx as ox

ROOT = Path(__file__).resolve().parents[1]

FILES = {
    "DRIVING": ROOT / "data" / "raw" /
    "roads_osm_20261011_115925.graphml",
    "WALKING": ROOT / "data" / "raw" /
    "roads_walking_osm_20261011_122708.graphml",
}

U = "5668292289"
V = "5668292290"
TARGET_OSMID = "594403473"


def load_graph(path):
    graph = ox.load_graphml(path)
    return nx.relabel_nodes(
        graph,
        {node: str(node) for node in graph.nodes},
        copy=True,
    )


def values(value):
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        return {str(item) for item in value}
    return {str(value)}


def main():
    graphs = {
        name: load_graph(path)
        for name, path in FILES.items()
    }

    for name, graph in graphs.items():
        print("\n" + "=" * 70)
        print(name)
        print(f"Nodes: {graph.number_of_nodes():,}")
        print(f"Edges: {graph.number_of_edges():,}")

        for a, b in ((U, V), (V, U)):
            print(f"\nEdges {a} -> {b}")

            if not graph.has_edge(a, b):
                print("  NONE")
            else:
                for key, data in graph.get_edge_data(a, b).items():
                    print(
                        f"  key={key}, "
                        f"osmid={data.get('osmid')}, "
                        f"length={data.get('length')}, "
                        f"highway={data.get('highway')}, "
                        f"oneway={data.get('oneway')}, "
                        f"reversed={data.get('reversed')}, "
                        f"geometry_present={data.get('geometry') is not None}"
                    )

        print("\nSearch all graph edges for OSM way", TARGET_OSMID)
        matches = 0

        for a, b, key, data in graph.edges(keys=True, data=True):
            if TARGET_OSMID in values(data.get("osmid")):
                matches += 1
                print(
                    f"  {a} -> {b}, key={key}, "
                    f"length={data.get('length')}, "
                    f"osmid={data.get('osmid')}, "
                    f"highway={data.get('highway')}, "
                    f"oneway={data.get('oneway')}, "
                    f"reversed={data.get('reversed')}"
                )

        print(f"Matching directed edges: {matches}")

        for node in (U, V):
            print(f"\nNeighbours of {node}")

            if node not in graph:
                print("  NODE MISSING")
                continue

            for other in sorted(
                set(graph.predecessors(node))
                | set(graph.successors(node))
            ):
                for a, b in ((node, other), (other, node)):
                    if not graph.has_edge(a, b):
                        continue

                    for key, data in graph.get_edge_data(a, b).items():
                        print(
                            f"  {a} -> {b}, key={key}, "
                            f"length={data.get('length')}, "
                            f"osmid={data.get('osmid')}, "
                            f"highway={data.get('highway')}"
                        )

    print("\nFinished. Graph files were not modified.")


if __name__ == "__main__":
    main()
