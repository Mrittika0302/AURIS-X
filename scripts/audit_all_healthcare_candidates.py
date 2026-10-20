
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import networkx as nx
import osmnx as ox

ROOT = Path(__file__).resolve().parents[1]

ACCESS = ROOT / "data/gold/healthcare_accessibility_by_population_cell.csv"
IMPACT = ROOT / "reports/candidate_impact_top10_20261012.csv"
DRIVE_GRAPH = ROOT / "data/raw/roads_osm_20261011_115925.graphml"
WALK_GRAPH = ROOT / "data/raw/roads_walking_osm_20261011_122708.graphml"

OUT_CSV = ROOT / "reports/candidate_impact_top10_audit_20261013.csv"
OUT_TXT = ROOT / "reports/candidate_impact_top10_audit_20261013.txt"

THRESHOLD_M = 5000.0
SNAP_WARNING_M = 250.0


def load_graph(path):
    if not path.exists():
        raise FileNotFoundError(f"Missing graph: {path}")

    graph = ox.load_graphml(path)
    graph = nx.relabel_nodes(graph, lambda n: str(n), copy=True)

    for _, _, _, data in graph.edges(keys=True, data=True):
        length = float(data.get("length", np.nan))
        if not np.isfinite(length) or length <= 0:
            raise ValueError(f"Invalid edge length in {path.name}")
        data["length"] = length

    return graph


def numeric_column(frame, column):
    return pd.to_numeric(frame[column], errors="coerce").to_numpy(
        dtype=float
    )


def candidate_distances(graph, node, population_nodes):
    if node not in graph:
        raise ValueError(f"Candidate node {node} is missing from graph")

    # Correct direction for population-to-candidate distances.
    reversed_graph = graph.reverse(copy=False)

    distances = nx.single_source_dijkstra_path_length(
        reversed_graph, node, weight="length"
    )

    return np.array(
        [distances.get(str(n), np.nan) for n in population_nodes],
        dtype=float,
    )


def crossing_mask(baseline, candidate_distance):
    # Match the original simulation's threshold-crossing definition.
    after = np.fmin(baseline, candidate_distance)

    return (
        np.isfinite(baseline)
        & (baseline > THRESHOLD_M)
        & np.isfinite(after)
        & (after <= THRESHOLD_M)
    )


def main():
    for path in [ACCESS, IMPACT, DRIVE_GRAPH, WALK_GRAPH]:
        if not path.exists():
            raise FileNotFoundError(f"Missing input: {path}")

    access = pd.read_csv(ACCESS, low_memory=False)
    impact = pd.read_csv(IMPACT, low_memory=False)

    required_access = [
        "population_cell_id",
        "drive_nearest_node_id",
        "walk_nearest_node_id",
        "driving_distance_m",
        "walking_distance_m",
    ]
    required_impact = [
        "rank",
        "candidate_zone_id",
        "drive_candidate_node_id",
        "walk_candidate_node_id",
        "drive_candidate_snap_m",
        "walk_candidate_snap_m",
        "driving_cells_moved_to_5km_or_less",
        "walking_cells_moved_to_5km_or_less",
    ]

    for col in required_access:
        if col not in access.columns:
            raise ValueError(f"Missing accessibility column: {col}")

    for col in required_impact:
        if col not in impact.columns:
            raise ValueError(f"Missing impact column: {col}")

    if access["population_cell_id"].duplicated().any():
        raise ValueError("Duplicate population_cell_id values found")

    if impact["candidate_zone_id"].duplicated().any():
        raise ValueError("Duplicate candidate_zone_id values found")

    if len(impact) != 10:
        raise ValueError(
            f"Expected 10 impact rows; found {len(impact)}"
        )

    access = access.reset_index(drop=True)
    impact = impact.sort_values("rank").reset_index(drop=True)

    print("Loading driving graph...")
    drive = load_graph(DRIVE_GRAPH)

    print("Loading walking graph...")
    walk = load_graph(WALK_GRAPH)

    drive_pop = access["drive_nearest_node_id"].astype(str).tolist()
    walk_pop = access["walk_nearest_node_id"].astype(str).tolist()

    missing_drive = sum(n not in drive for n in drive_pop)
    missing_walk = sum(n not in walk for n in walk_pop)

    if missing_drive or missing_walk:
        raise ValueError(
            "Population node IDs missing from graph: "
            f"driving={missing_drive}, walking={missing_walk}"
        )

    drive_before = numeric_column(access, "driving_distance_m")
    walk_before = numeric_column(access, "walking_distance_m")

    rows = []
    report_lines = [
        "AURIS-X HEALTHCARE CANDIDATE IMPACT AUDIT",
        f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        f"Population cells: {len(access)}",
        f"Candidates checked: {len(impact)}",
        f"Threshold: {THRESHOLD_M:.0f} m",
        f"Snap review threshold: {SNAP_WARNING_M:.0f} m",
        "",
        "Candidate-by-candidate results",
        "=" * 72,
    ]

    all_membership_equal = True
    all_counts_match = True
    all_nodes_valid = True

    for _, candidate in impact.iterrows():
        rank = int(candidate["rank"])
        cid = str(candidate["candidate_zone_id"])
        dn = str(candidate["drive_candidate_node_id"])
        wn = str(candidate["walk_candidate_node_id"])

        print(f"Auditing rank {rank}: {cid}")

        if dn not in drive or wn not in walk:
            all_nodes_valid = False
            raise ValueError(
                f"{cid}: candidate node missing from its graph"
            )

        drive_new = candidate_distances(drive, dn, drive_pop)
        walk_new = candidate_distances(walk, wn, walk_pop)

        drive_cross = crossing_mask(drive_before, drive_new)
        walk_cross = crossing_mask(walk_before, walk_new)

        drive_count = int(drive_cross.sum())
        walk_count = int(walk_cross.sum())
        different_cells = int(np.count_nonzero(
            drive_cross != walk_cross
        ))

        reported_drive = int(
            candidate["driving_cells_moved_to_5km_or_less"]
        )
        reported_walk = int(
            candidate["walking_cells_moved_to_5km_or_less"]
        )

        counts_match = (
            drive_count == reported_drive
            and walk_count == reported_walk
        )
        membership_equal = different_cells == 0
        nodes_equal = dn == wn

        drive_snap = float(candidate["drive_candidate_snap_m"])
        walk_snap = float(candidate["walk_candidate_snap_m"])

        drive_snap_review = drive_snap > SNAP_WARNING_M
        walk_snap_review = walk_snap > SNAP_WARNING_M

        all_counts_match &= counts_match
        all_membership_equal &= membership_equal

        row = {
            "rank": rank,
            "candidate_zone_id": cid,
            "drive_node_id": dn,
            "walk_node_id": wn,
            "candidate_nodes_equal": nodes_equal,
            "candidate_nodes_exist": True,
            "recomputed_driving_crossings": drive_count,
            "reported_driving_crossings": reported_drive,
            "recomputed_walking_crossings": walk_count,
            "reported_walking_crossings": reported_walk,
            "different_crossing_cells_between_modes": different_cells,
            "crossing_membership_equal": membership_equal,
            "reported_counts_match": counts_match,
            "drive_candidate_snap_m": drive_snap,
            "walk_candidate_snap_m": walk_snap,
            "drive_snap_review_over_250m": drive_snap_review,
            "walk_snap_review_over_250m": walk_snap_review,
            "driving_candidate_reachable_cells": int(
                np.isfinite(drive_new).sum()
            ),
            "walking_candidate_reachable_cells": int(
                np.isfinite(walk_new).sum()
            ),
        }
        rows.append(row)

        report_lines.append(
            f"Rank {rank}: {cid}\n"
            f"  Candidate nodes equal: {nodes_equal}\n"
            f"  Driving crossings: {drive_count} "
            f"(reported {reported_drive})\n"
            f"  Walking crossings: {walk_count} "
            f"(reported {reported_walk})\n"
            f"  Different crossing-cell memberships: "
            f"{different_cells}\n"
            f"  Reported counts match: {counts_match}\n"
            f"  Driving snap: {drive_snap:.2f} m "
            f"(review={drive_snap_review})\n"
            f"  Walking snap: {walk_snap:.2f} m "
            f"(review={walk_snap_review})\n"
            f"  Candidate-reachable population nodes: "
            f"driving={row['driving_candidate_reachable_cells']}, "
            f"walking={row['walking_candidate_reachable_cells']}\n"
        )

    result = pd.DataFrame(rows)

    report_lines.extend([
        "=" * 72,
        "OVERALL AUDIT",
        f"All reported crossing counts match: {all_counts_match}",
        f"All 10 candidates have identical crossing-cell membership "
        f"between modes: {all_membership_equal}",
        f"All candidate nodes were valid: {all_nodes_valid}",
        "",
        "Snap-review candidates:",
    ])

    review_rows = result[
        result["drive_snap_review_over_250m"]
        | result["walk_snap_review_over_250m"]
    ]

    if review_rows.empty:
        report_lines.append("None")
    else:
        for _, row in review_rows.iterrows():
            report_lines.append(
                f"{row['candidate_zone_id']}: "
                f"driving={row['drive_candidate_snap_m']:.2f} m, "
                f"walking={row['walk_candidate_snap_m']:.2f} m"
            )

    report_lines.extend([
        "",
        "Interpretation notes:",
        "- Identical counts do not prove identical cell membership.",
        "- Equal candidate node IDs do not prove identical networks.",
        "- Network distances are not travel times.",
        "- The 5 km threshold is a preliminary analysis assumption.",
        "- Candidate centroids are not verified buildable parcels.",
        "- This is a model audit, not real-world access validation.",
        "",
        "Existing impact CSV and JSON were not modified by this audit.",
    ])

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUT_CSV, index=False)
    OUT_TXT.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )

    print("\nAUDIT COMPLETE")
    print(f"Detailed CSV: {OUT_CSV}")
    print(f"Text report: {OUT_TXT}")
    print(f"All reported counts match: {all_counts_match}")
    print(
        "All 10 crossing-cell memberships equal across modes: "
        f"{all_membership_equal}"
    )
    print("\nSnap-review candidates:")
    print(
        result.loc[
            result["drive_snap_review_over_250m"]
            | result["walk_snap_review_over_250m"],
            [
                "rank",
                "candidate_zone_id",
                "drive_candidate_snap_m",
                "walk_candidate_snap_m",
            ],
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
