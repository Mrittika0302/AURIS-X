
from pathlib import Path
import json
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)

report = {
    "report": "AURIS-X Road Graph Quality Assurance",
    "created_at": datetime.now().isoformat(timespec="seconds"),
    "study_area": {
        "south": 10.85,
        "west": 76.85,
        "north": 11.15,
        "east": 77.15,
        "note": (
            "Approximate bounding box, not an official "
            "Coimbatore administrative boundary."
        ),
    },
    "graphs": {
        "driving": {
            "file": "roads_osm_20261011_115925.graphml",
            "nodes": 84306,
            "edges": 211237,
            "largest_weak_component_nodes": 83443,
            "invalid_or_nonpositive_edge_lengths": 0,
        },
        "walking": {
            "file": "roads_walking_osm_20261011_122708.graphml",
            "nodes": 86421,
            "edges": 220868,
            "largest_weak_component_nodes": 85828,
            "invalid_or_nonpositive_edge_lengths": 0,
        },
    },
    "overlap_analysis": {
        "shared_directed_node_pairs": 208324,
        "driving_only_directed_pairs": 1601,
        "walking_only_directed_pairs": 11068,
        "shared_pairs_with_lengths_equal_within_1cm": 208300,
        "important_caveat": (
            "Comparison used minimum edge length per directed "
            "node pair; it does not establish full equivalence "
            "of parallel edges or road access."
        ),
    },
    "anomaly_inspection": {
        "anomalous_pairs_reviewed": 4,
        "additional_segmentation_example_reviewed": True,
        "findings": [
            {
                "pair": "6965421644 <-> 6965421653",
                "finding": (
                    "Parallel residential and primary-road "
                    "edges connect the same endpoint nodes."
                ),
            },
            {
                "pair": "9068977797 <-> 9068977796",
                "finding": (
                    "Parallel residential edges of different "
                    "lengths exist; the shorter edge has no "
                    "stored geometry attribute."
                ),
            },
            {
                "pair": "5655107628 <-> 9676768874",
                "finding": (
                    "Parallel unclassified and primary-road "
                    "edges connect the same endpoint nodes."
                ),
            },
            {
                "pair": "13999738633 <-> 13999738634",
                "finding": (
                    "Parallel residential and primary-road "
                    "edges connect the same endpoint nodes."
                ),
            },
            {
                "pair": "5668292289 <-> 5668292290",
                "finding": (
                    "A residential road segment is represented "
                    "as one edge in driving and split into two "
                    "edges in walking. This is consistent with "
                    "different graph segmentation."
                ),
            },
        ],
        "conclusion": (
            "The inspected differences are structurally "
            "plausible, but this does not prove real-world "
            "road correctness."
        ),
    },
    "healthcare_accessibility_validation": {
        "sampled_cells": 30,
        "driving_saved_distances_matched": 30,
        "walking_saved_distances_matched": 30,
        "nearest_facility_assignment_checks_passed": True,
        "scope_note": (
            "Sampled computational validation only; not "
            "independent real-world validation."
        ),
    },
    "limitations": [
        "OSM road completeness and access restrictions have "
        "not been independently verified.",
        "Missing edge geometry does not by itself establish "
        "an invalid edge.",
        "Network distances are distances, not travel times.",
        "The study-area bounding box is approximate.",
        "Healthcare facility operational status has not been "
        "independently verified.",
        "Accessibility results depend on the selected road "
        "network, facility locations, and snapping process.",
    ],
    "recommendation": (
        "Do not rebuild the graphs solely because of the "
        "inspected parallel-edge differences. Preserve the "
        "current outputs. Perform targeted external or "
        "field validation before treating candidate-site "
        "rankings as real-world recommendations."
    ),
    "files_modified_by_this_script": [
        "reports/road_graph_qa_summary.json",
        "reports/road_graph_qa_summary.txt",
    ],
}

json_path = REPORTS / "road_graph_qa_summary.json"
txt_path = REPORTS / "road_graph_qa_summary.txt"

with open(json_path, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

lines = [
    "AURIS-X ROAD GRAPH QUALITY ASSURANCE REPORT",
    "=" * 48,
    "",
    f"Created: {report['created_at']}",
    "",
    "1. GRAPH SIZES",
    (
        "Driving: 84,306 nodes; 211,237 edges; "
        "83,443 nodes in largest weak component."
    ),
    (
        "Walking: 86,421 nodes; 220,868 edges; "
        "85,828 nodes in largest weak component."
    ),
    "No invalid or non-positive edge lengths were detected.",
    "",
    "2. GRAPH OVERLAP",
    "Shared directed node pairs: 208,324",
    "Driving-only directed pairs: 1,601",
    "Walking-only directed pairs: 11,068",
    (
        "Of shared pairs, 208,300 had minimum lengths "
        "equal within 1 cm."
    ),
    (
        "Caveat: this compares minimum edge length per "
        "directed pair, not all parallel edges."
    ),
    "",
    "3. ANOMALY INSPECTION",
]

for item in report["anomaly_inspection"]["findings"]:
    lines.append(f"- {item['pair']}: {item['finding']}")

lines.extend([
    "",
    "4. ACCESSIBILITY COMPUTATIONAL VALIDATION",
    "Driving sample: 30/30 saved distances matched.",
    "Walking sample: 30/30 saved distances matched.",
    "Nearest-facility assignment sample checks passed.",
    "These checks do not prove real-world accuracy.",
    "",
    "5. LIMITATIONS",
])

for limitation in report["limitations"]:
    lines.append(f"- {limitation}")

lines.extend([
    "",
    "6. RECOMMENDATION",
    report["recommendation"],
    "",
    "This report documents existing diagnostics.",
    "It does not rebuild graphs or recalculate accessibility.",
])

with open(txt_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print("Road graph QA report created successfully.")
print(f"JSON: {json_path}")
print(f"Text: {txt_path}")
print("Existing graphs and healthcare outputs were not modified.")
