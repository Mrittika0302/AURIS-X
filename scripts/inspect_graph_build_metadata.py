
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

def main():
    for label, path in FILES.items():
        print("\n" + "=" * 65)
        print(label)
        print("File:", path)
        print("Exists:", path.exists())

        graph = ox.load_graphml(path)

        print("\nGraph metadata:")
        for key, value in graph.graph.items():
            print(f"  {key}: {value}")

        print("\nGraph structure:")
        print("  Directed:", graph.is_directed())
        print("  Multigraph:", graph.is_multigraph())
        print("  Nodes:", graph.number_of_nodes())
        print("  Edges:", graph.number_of_edges())

        print("\nNode attribute examples:")
        for node, attrs in list(graph.nodes(data=True))[:3]:
            print(f"  {node}: {attrs}")

        print("\nEdge attribute examples:")
        for u, v, key, attrs in list(
            graph.edges(keys=True, data=True)
        )[:3]:
            print(f"  {u} -> {v}, key={key}: {attrs}")

    print("\nFinished. No graph files modified.")

if __name__ == "__main__":
    main()
