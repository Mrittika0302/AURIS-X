
from pathlib import Path
import glob
import os
import networkx as nx

# ============================================================
# AURIS-X: Compare OSM way topology in driving and walking graphs
# Read-only diagnostic. Does not modify graph or gold outputs.
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"

TARGET_OSMID = "1262117427"


def latest_graph(pattern):
    """Find the newest graph file matching a pattern."""
    files = glob.glob(str(RAW_DIR / pattern))

    if not files:
        raise FileNotFoundError(
            f"No graph found matching {pattern} in {RAW_DIR}"
        )

    return max(files, key=os.path.getmtime)


def normalise_osmid(value):
    """Convert OSM IDs to a consistent set of strings."""
    if value is None:
        return set()

    if isinstance(value, (list, tuple, set)):
        result = set()
        for item in value:
            result.update(normalise_osmid(item))
        return result

    return {str(value)}


def edge_osmids(data):
    """Return OSM IDs from an edge's attributes."""
    return normalise_osmid(data.get("osmid"))


def load_graph(path):
    """Load a GraphML file without modifying it."""
    print(f"\nLoading: {Path(path).name}")
    graph = nx.read_graphml(path)
    print(
        f"Graph loaded: {graph.number_of_nodes():,} nodes, "
        f"{graph.number_of_edges():,} edges"
    )
    return graph


def inspect_target_way(graph, label):
    """
    Find directed edges whose osmid attribute contains TARGET_OSMID.
    Return directed and undirected endpoint-pair sets.
    """
    directed_pairs = set()
    undirected_pairs = set()
    matching_edges = []
    total_length = 0.0

    for u, v, key, data in graph.edges(keys=True, data=True):
        ids = edge_osmids(data)

        if TARGET_OSMID not in ids:
            continue

        u_str = str(u)
        v_str = str(v)

        directed_pairs.add((u_str, v_str))
        undirected_pairs.add(tuple(sorted((u_str, v_str))))

        try:
            length = float(data.get("length", 0.0))
        except (TypeError, ValueError):
            length = 0.0

        total_length += length

        matching_edges.append({
            "u": u_str,
            "v": v_str,
            "key": str(key),
            "length": length,
            "osmid": data.get("osmid"),
            "highway": data.get("highway"),
            "name": data.get("name"),
        })

    print(f"\n{'=' * 65}")
    print(f"{label.upper()} GRAPH")
    print(f"{'=' * 65}")
    print(f"Target OSM way ID: {TARGET_OSMID}")
    print(f"Matching directed edge records: {len(matching_edges)}")
    print(f"Unique directed endpoint pairs: {len(directed_pairs)}")
    print(f"Unique undirected endpoint pairs: {len(undirected_pairs)}")
    print(f"Sum of matching directed edge lengths: {total_length:,.2f} m")

    if matching_edges:
        print("\nFirst 10 matching edge records:")

        for edge in matching_edges[:10]:
            print(
                f"  {edge['u']} -> {edge['v']} | "
                f"length={edge['length']:.3f} m | "
                f"osmid={edge['osmid']} | "
                f"highway={edge['highway']} | "
                f"name={edge['name']}"
            )
    else:
        print("WARNING: No matching edges found for this OSM way ID.")

    return {
        "directed_pairs": directed_pairs,
        "undirected_pairs": undirected_pairs,
        "matching_edges": matching_edges,
        "total_length": total_length,
    }


def print_pair_comparison(drive, walk):
    """Compare endpoint pairs containing the target way."""
    drive_directed = drive["directed_pairs"]
    walk_directed = walk["directed_pairs"]

    drive_undirected = drive["undirected_pairs"]
    walk_undirected = walk["undirected_pairs"]

    print(f"\n{'=' * 65}")
    print("CROSS-GRAPH COMPARISON")
    print(f"{'=' * 65}")

    print("\nDirected endpoint pairs:")
    print(f"  Shared:       {len(drive_directed & walk_directed)}")
    print(f"  Driving-only: {len(drive_directed - walk_directed)}")
    print(f"  Walking-only: {len(walk_directed - drive_directed)}")

    print("\nUndirected endpoint pairs:")
    print(f"  Shared:       {len(drive_undirected & walk_undirected)}")
    print(f"  Driving-only: {len(drive_undirected - walk_undirected)}")
    print(f"  Walking-only: {len(walk_undirected - drive_undirected)}")

    walk_only = sorted(walk_undirected - drive_undirected)

    if walk_only:
        print("\nFirst 15 walking-only undirected endpoint pairs:")

        for u, v in walk_only[:15]:
            print(f"  {u} <-> {v}")

    drive_only = sorted(drive_undirected - walk_undirected)

    if drive_only:
        print("\nFirst 15 driving-only undirected endpoint pairs:")

        for u, v in drive_only[:15]:
            print(f"  {u} <-> {v}")

    print("\nInterpretation:")
    print(
        "Different endpoint pairs do not automatically mean a road is "
        "missing. OSMnx may simplify or segment the same OSM way "
        "differently in driving and walking graphs."
    )
    print(
        "The length sum is a diagnostic count of matching directed edge "
        "records, not a physical road-length estimate."
    )


def main():
    print("AURIS-X OSM WAY TOPOLOGY DIAGNOSTIC")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Target OSM way: {TARGET_OSMID}")
    print("Mode: READ-ONLY")

    drive_path = latest_graph("roads_osm_*.graphml")
    walk_path = latest_graph("roads_walking_osm_*.graphml")

    print(f"\nDriving graph file: {Path(drive_path).name}")
    print(f"Walking graph file: {Path(walk_path).name}")

    drive_graph = load_graph(drive_path)
    walk_graph = load_graph(walk_path)

    drive_results = inspect_target_way(drive_graph, "Driving")
    walk_results = inspect_target_way(walk_graph, "Walking")

    print_pair_comparison(drive_results, walk_results)

    print("\nDiagnostic completed. No files were modified.")


if __name__ == "__main__":
    main()
