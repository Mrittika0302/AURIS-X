
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

ACCESS_FILE = (
    ROOT
    / "data"
    / "gold"
    / "healthcare_accessibility_by_population_cell.csv"
)

FACILITY_FILE = (
    ROOT
    / "data"
    / "silver"
    / "healthcare_network_matches_20261011_122708.csv"
)


def normalize_id(series):
    """Normalize OSM IDs read as numbers or strings."""
    return (
        series.astype("string")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )


def main():
    print("AURIS-X Assigned Facility ID Audit")
    print("Read-only: no existing files will be modified.")
    print()

    # Verify input files.
    for file_path in (ACCESS_FILE, FACILITY_FILE):
        if not file_path.exists():
            raise FileNotFoundError(
                f"Required input file not found:\n{file_path}"
            )

    access = pd.read_csv(ACCESS_FILE)
    facilities = pd.read_csv(
        FACILITY_FILE,
        dtype={"osm_id": "string"},
    )

    required_access_columns = [
        "driving_distance_m",
        "driving_facility_id",
        "walking_distance_m",
        "walking_facility_id",
    ]

    required_facility_columns = [
        "osm_id",
        "name",
        "category",
        "drive_nearest_node_id",
        "walk_nearest_node_id",
    ]

    missing_access = [
        column
        for column in required_access_columns
        if column not in access.columns
    ]

    missing_facilities = [
        column
        for column in required_facility_columns
        if column not in facilities.columns
    ]

    if missing_access:
        raise ValueError(
            f"Accessibility file is missing columns: {missing_access}"
        )

    if missing_facilities:
        raise ValueError(
            f"Facility file is missing columns: {missing_facilities}"
        )

    facilities = facilities.copy()
    facilities["osm_id"] = normalize_id(facilities["osm_id"])

    print(f"Accessibility rows: {len(access):,}")
    print(f"Facility source records: {len(facilities):,}")

    for mode in ("driving", "walking"):
        print()
        print("=" * 65)
        print(f"{mode.upper()} FACILITY ID AUDIT")
        print("=" * 65)

        id_column = f"{mode}_facility_id"
        distance_column = f"{mode}_distance_m"

        if mode == "driving":
            node_column = "drive_nearest_node_id"
        else:
            node_column = "walk_nearest_node_id"

        # Consider rows with both a distance and an assigned facility ID.
        rows = access.loc[
            access[distance_column].notna()
            & access[id_column].notna(),
            [id_column, distance_column],
        ].copy()

        rows["_normalized_id"] = normalize_id(rows[id_column])

        source = facilities[
            ["osm_id", node_column, "name", "category"]
        ].copy()

        source["_normalized_id"] = normalize_id(source["osm_id"])

        # IDs can theoretically have multiple source records, so preserve
        # all matching records instead of assuming IDs are unique.
        merged = rows.merge(
            source,
            on="_normalized_id",
            how="left",
            suffixes=("_assigned", "_source"),
            indicator=True,
        )

        matched_rows = merged["_merge"].eq("both")
        unmatched_rows = ~matched_rows

        assigned_ids = set(rows["_normalized_id"].dropna())
        source_ids = set(source["_normalized_id"].dropna())
        absent_ids = sorted(assigned_ids - source_ids)

        print(
            "Rows with both assigned facility ID and distance: "
            f"{len(rows):,}"
        )
        print(
            "Rows whose assigned ID exists in the facility source: "
            f"{int(matched_rows.sum()):,}"
        )
        print(
            "Rows whose assigned ID has no source match: "
            f"{int(unmatched_rows.sum()):,}"
        )
        print(
            "Distinct assigned IDs absent from source: "
            f"{len(absent_ids):,}"
        )

        if absent_ids:
            print("Examples of absent IDs:")
            for osm_id in absent_ids[:10]:
                print(f"  {osm_id}")

        duplicate_source_mask = source[
            "_normalized_id"
        ].duplicated(keep=False)

        print(
            "Facility source rows with duplicate OSM IDs: "
            f"{int(duplicate_source_mask.sum()):,}"
        )

        # Show a few assignments for manual inspection.
        print()
        print("Sample assignments:")
        sample_columns = [
            "_normalized_id",
            distance_column,
            node_column,
            "name",
            "category",
            "_merge",
        ]

        sample_columns = [
            column
            for column in sample_columns
            if column in merged.columns
        ]

        print(
            merged[sample_columns]
            .head(10)
            .to_string(index=False)
        )

        print()
        print(
            "Important: this audit checks whether assigned IDs exist in "
            "the source data. It does not independently prove that each "
            "facility is the nearest one or that its ID corresponds to "
            "the exact graph node selected by routing."
        )

    print()
    print("Audit complete. No files were created or modified.")


if __name__ == "__main__":
    main()
