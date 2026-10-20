
import glob
import json
from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# AURIS-X | PHASE 2: EDUCATION ACCESSIBILITY FINALIZATION
#
# Creates:
#   reports/education_phase2_completion_<timestamp>.md
#   reports/education_phase2_completion_manifest_<timestamp>.json
#
# Read-only inventory of existing data.
# Does not modify healthcare datasets, graphs, or scripts.
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

RAW = ROOT / "data" / "raw"
SILVER = ROOT / "data" / "silver"
GOLD = ROOT / "data" / "gold"
REPORTS = ROOT / "reports"

# Confirmations supplied by the project owner.
MAP_MARKERS_VERIFIED = True
EDUCATION_VALIDATION_COMPLETED = True
SENSITIVITY_TESTING_COMPLETED = True


def latest_file(pattern):
    """Return the most recently modified matching file."""
    paths = [Path(p) for p in glob.glob(str(pattern))]
    paths = [p for p in paths if p.is_file()]

    if not paths:
        return None

    return max(paths, key=lambda p: p.stat().st_mtime)


def inventory(patterns):
    """List matching files without changing their contents."""
    found = {}

    for pattern in patterns:
        for item in glob.glob(str(pattern)):
            path = Path(item)

            if not path.is_file():
                continue

            key = str(path.resolve()).lower()

            found[key] = {
                "path": path.relative_to(ROOT).as_posix(),
                "size_bytes": path.stat().st_size,
                "modified_at_utc": datetime.fromtimestamp(
                    path.stat().st_mtime,
                    timezone.utc,
                ).isoformat(),
            }

    return sorted(
        found.values(),
        key=lambda item: item["path"].lower(),
    )


def describe(path):
    """Return a portable relative path, or None."""
    if path is None:
        return None

    return path.relative_to(ROOT).as_posix()


def main():
    REPORTS.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    # --------------------------------------------------------
    # Find the latest required education outputs.
    # --------------------------------------------------------
    required = {
        "Education priority zones": latest_file(
            GOLD / "education_priority_zones_*.csv"
        ),
        "Education top-20 mapped zones": latest_file(
            GOLD / "education_priority_zones_mapped_top20_*.csv"
        ),
        "Education accessibility grid": latest_file(
            GOLD / "education_accessibility_by_population_cell_*.csv"
        ),
        "Education accessibility flags": latest_file(
            GOLD / "education_accessibility_flags_*.csv"
        ),
        "Education underserved cells": latest_file(
            GOLD / "education_underserved_cells_*.csv"
        ),
        "Education priority-zone map": latest_file(
            REPORTS / "education_priority_zones_map_*.html"
        ),
    }

    missing = [
        name for name, path in required.items()
        if path is None
    ]

    # --------------------------------------------------------
    # Inventory education-specific project files.
    # --------------------------------------------------------
    raw_files = inventory([
        str(RAW / "education_*.json"),
        str(RAW / "education_*.csv"),
    ])

    silver_files = inventory([
        str(SILVER / "education_*.csv"),
    ])

    gold_files = inventory([
        str(GOLD / "education_*.csv"),
    ])

    report_files = inventory([
        str(REPORTS / "education_*.json"),
        str(REPORTS / "education_*.csv"),
        str(REPORTS / "education_*.txt"),
        str(REPORTS / "education_*.html"),
    ])

    # Validation and sensitivity-test evidence should be
    # reviewed separately; this script does not rerun tests.
    review_keywords = (
        "validation",
        "sensitivity",
        "network_review",
        "review",
        "qa",
    )

    evidence_files = [
        item for item in report_files
        if any(
            keyword in item["path"].lower()
            for keyword in review_keywords
        )
    ]

    if (
        not missing
        and MAP_MARKERS_VERIFIED
        and EDUCATION_VALIDATION_COMPLETED
        and SENSITIVITY_TESTING_COMPLETED
    ):
        status = "READY_FOR_FINAL_REVIEW"
    else:
        status = "REQUIRES_REVIEW"

    report_path = REPORTS / (
        f"education_phase2_completion_{timestamp}.md"
    )

    manifest_path = REPORTS / (
        f"education_phase2_completion_manifest_{timestamp}.json"
    )

    # --------------------------------------------------------
    # Write Markdown report.
    # --------------------------------------------------------
    lines = [
        "# AURIS-X Phase 2: Education Accessibility",
        "",
        f"Generated (UTC): {datetime.now(timezone.utc).isoformat()}",
        "",
        f"**Status: {status}**",
        "",
        "## 1. Project-owner confirmations",
        "",
        f"- All 20 map markers visible: "
        f"{'Yes' if MAP_MARKERS_VERIFIED else 'No'}",
        f"- Education validation completed: "
        f"{'Reported complete' if EDUCATION_VALIDATION_COMPLETED else 'Not complete'}",
        f"- Sensitivity testing completed: "
        f"{'Reported complete' if SENSITIVITY_TESTING_COMPLETED else 'Not complete'}",
        "",
        "These are project-owner confirmations. This script does not "
        "independently rerun validation or sensitivity tests.",
        "",
        "## 2. Required output inventory",
        "",
    ]

    for name, path in required.items():
        if path is None:
            lines.append(f"- **MISSING:** {name}")
        else:
            lines.append(f"- **Found — {name}:** `{describe(path)}`")

    lines.extend([
        "",
        "## 3. Education data inventory",
        "",
        f"- Raw education files: {len(raw_files)}",
        f"- Silver education files: {len(silver_files)}",
        f"- Gold education files: {len(gold_files)}",
        f"- Education reports and maps: {len(report_files)}",
        f"- Potential review/evidence files by filename: {len(evidence_files)}",
        "",
        "### Potential review/evidence files",
        "",
    ])

    if evidence_files:
        lines.extend(
            f"- `{item['path']}`" for item in evidence_files
        )
    else:
        lines.append(
            "No files matched the evidence filename patterns. "
            "This does not prove that validation evidence is absent; "
            "check your actual filenames and folders."
        )

    lines.extend([
        "",
        "## 4. Analytical limitations",
        "",
        "- The study-area bounding box is approximate, not an official boundary.",
        "- OpenStreetMap coverage and facility validity are not independently guaranteed.",
        "- Population raster units remain unverified; do not treat raster values as confirmed headcounts.",
        "- Network distances are metres, not travel times.",
        "- The 5 km threshold is preliminary, not an official standard.",
        "- Raster-block priority zones are not official neighbourhoods or confirmed construction sites.",
        "- A large snapping distance is a review flag, not automatically a failed match.",
        "",
        "## 5. Healthcare phase protection",
        "",
        "This script inventories education files and writes two new education "
        "completion files. It does not edit healthcare datasets, road graphs, "
        "or healthcare scripts.",
        "",
        "## 6. Final sign-off",
        "",
    ])

    if missing:
        lines.append(
            "**Do not close Phase 2 yet.** Required outputs were not found:"
        )
        lines.extend(f"- {name}" for name in missing)
    else:
        lines.append(
            "All required output filename patterns were found. Review the "
            "listed outputs and the actual validation/sensitivity evidence "
            "before formally freezing Phase 2."
        )

    lines.extend([
        "",
        "After review, preserve the report and manifest with the frozen "
        "education outputs. Make future corrections through clearly versioned "
        "files rather than silently overwriting frozen results.",
        "",
    ])

    report_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # Write machine-readable manifest.
    # --------------------------------------------------------
    manifest = {
        "project": "AURIS-X",
        "phase": 2,
        "phase_name": "Education Accessibility",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "owner_confirmations": {
            "all_20_map_markers_visible": MAP_MARKERS_VERIFIED,
            "education_validation_completed": EDUCATION_VALIDATION_COMPLETED,
            "sensitivity_testing_completed": SENSITIVITY_TESTING_COMPLETED,
        },
        "missing_required_outputs": missing,
        "required_outputs": {
            name: describe(path)
            for name, path in required.items()
        },
        "inventories": {
            "raw": raw_files,
            "silver": silver_files,
            "gold": gold_files,
            "reports": report_files,
            "potential_validation_evidence": evidence_files,
        },
        "completion_report": describe(report_path),
        "manifest_path": describe(manifest_path),
        "healthcare_files_modified": False,
        "notes": [
            "File inventory is based on filenames and filesystem metadata.",
            "Validation and sensitivity testing were reported by the project owner; this script does not rerun them.",
            "Review the actual sensitivity-test evidence before final sign-off.",
            "Population raster units are unverified.",
            "The 5 km threshold is preliminary.",
        ],
    }

    manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # Console summary.
    # --------------------------------------------------------
    print("=" * 64)
    print("AURIS-X PHASE 2 FINALIZATION")
    print("=" * 64)
    print(f"Status: {status}")
    print(f"Raw education files: {len(raw_files)}")
    print(f"Silver education files: {len(silver_files)}")
    print(f"Gold education files: {len(gold_files)}")
    print(f"Education reports/maps: {len(report_files)}")
    print()
    print("Required outputs:")

    for name, path in required.items():
        result = f"FOUND: {describe(path)}" if path else "MISSING"
        print(f"  {name}: {result}")

    if missing:
        print("\nResolve missing outputs before closing Phase 2.")

    print(f"\nCompletion report:\n  {report_path}")
    print(f"\nManifest:\n  {manifest_path}")
    print("\nHealthcare files were not modified.")
    print("Review the report before formally freezing Phase 2.")


if __name__ == "__main__":
    main()
