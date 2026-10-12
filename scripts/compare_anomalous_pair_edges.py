
from pathlib import Path
import ast
import pandas as pd
import networkx as nx
import osmnx as ox

ROOT = Path(__file__).resolve().parents[1]

DRIVE_FILE = ROOT / "data" / "raw" / "roads_osm_20261011_115925.graphml"
WALK_FILE = ROOT / "data" / "raw" / "roads_walking_osm_20261011_122708.graphml"
AUDIT_FILE = ROOT / "reports" / "parallel_edge_anomaly_audit.csv"
OUTPUT_FILE = ROOT / "reports" / "anomalous_pair_edge_comparison.csv"


def load_graph(path):
    graph = ox.load_graphml(path)
    return nx.relabel_nodes(
        graph,
        {n: str(n) for n in graph.nodes},
        copy=True,
    )


def parse_osmid(value):
    if value is None:
        return set()

    if isinstance(value, (list, tuple, set)):
        return {str(x) for x in value}

    if isinstance(value, float) and pd.isna(value):
        return set()

    if isinstance(value, str):
        text = value.strip()
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, (list, tuple, set)):
                return {str(x) for x in parsed}
            return {str(parsed)}
        except (ValueError, SyntaxError):
            return {text}

    return {str(value)}


def edge_summary(graph, u, v):
    if not graph.has_edge(u, v):
        return {
            "edge_count": 0,
            "min_length": None,
            "max_length": None,
            "osmids": set(),
            "lengths": [],
        }

    edges = list(graph.get_edge_data(u, v).values())
    lengths = [
        float(data["length"])
        for data in edges
        if data.get("length") is not None
    ]

    osmids = set()
    for data in edges:
        osmids.update(parse_osmid(data.get("osmid")))

    return {
        "edge_count": len(edges),
        "min_length": min(lengths) if lengths else None,
        "max_length": max(lengths) if lengths else None,
        "osmids": osmids,
        "lengths": lengths,
    }


def main():
    if not AUDIT_FILE.exists():
        raise FileNotFoundError(
            f"Audit file not found: {AUDIT_FILE}"
        )

    audit = pd.read_csv(AUDIT_FILE)

    required = {"u", "v"}
    missing = required - set(audit.columns)
    if missing:
        raise ValueError(
            f"Audit CSV lacks columns {sorted(missing)}. "
            f"Available columns: {list(audit.columns)}"
        )

    drive = load_graph(DRIVE_FILE)
    walk = load_graph(WALK_FILE)

    results = []

    for _, row in audit.iterrows():
        u, v = str(row["u"]), str(row["v"])

        d = edge_summary(drive, u, v)
        w = edge_summary(walk, u, v)

        shared_osmids = d["osmids"] & w["osmids"]
        drive_only_osmids = d["osmids"] - w["osmids"]
        walk_only_osmids = w["osmids"] - d["osmids"]

        results.append({
            "u": u,
            "v": v,
            "drive_edge_count": d["edge_count"],
            "walk_edge_count": w["edge_count"],
            "drive_min_length_m": d["min_length"],
            "walk_min_length_m": w["min_length"],
            "min_length_difference_m": (
                abs(d["min_length"] - w["min_length"])
                if d["min_length"] is not None
                and w["min_length"] is not None
                else None
            ),
            "drive_osmids": ";".join(sorted(d["osmids"])),
            "walk_osmids": ";".join(sorted(w["osmids"])),
            "shared_osmids": ";".join(sorted(shared_osmids)),
            "drive_only_osmids": ";".join(
                sorted(drive_only_osmids)
            ),
            "walk_only_osmids": ";".join(
                sorted(walk_only_osmids)
            ),
            "same_osmid_set": d["osmids"] == w["osmids"],
            "same_edge_count": d["edge_count"] == w["edge_count"],
        })

    result = pd.DataFrame(results)
    result.to_csv(OUTPUT_FILE, index=False)

    print(f"Pairs examined: {len(result)}")
    print(f"Output: {OUTPUT_FILE}")
    print("\nSummary:")
    print("Same OSM ID set:", int(result["same_osmid_set"].sum()))
    print("Same edge count:", int(result["same_edge_count"].sum()))
    print(
        "Pairs with different minimum lengths:",
        int((result["min_length_difference_m"] > 0.01).sum()),
    )

    print("\nLargest minimum-length differences:")
    columns = [
        "u", "v", "drive_min_length_m",
        "walk_min_length_m", "min_length_difference_m",
        "drive_osmids", "walk_osmids",
        "same_osmid_set", "same_edge_count",
    ]
    print(
        result.sort_values(
            "min_length_difference_m",
            ascending=False,
        )[columns].head(15).to_string(index=False)
    )


if __name__ == "__main__":
    main()
