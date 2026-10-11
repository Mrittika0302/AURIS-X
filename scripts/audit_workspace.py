
from pathlib import Path
import json
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent

EXPECTED_FOLDERS = [
    "docs",
    "scripts",
    "reports",
    "data/raw",
    "data/bronze",
    "data/silver",
    "data/gold",
    "data/boundaries",
    "data/population",
    "data/roads",
    "data/facilities",
]

DATA_EXTENSIONS = {
    ".csv", ".tsv", ".json", ".geojson",
    ".gpkg", ".shp", ".shx", ".dbf",
    ".prj", ".tif", ".tiff", ".xlsx", ".parquet",
    ".zip",
}


def main():
    print("=" * 60)
    print("AURIS-X | WORKSPACE AUDIT")
    print("=" * 60)
    print(f"Project root: {PROJECT_ROOT}")
    print()

    missing_folders = []

    for folder in EXPECTED_FOLDERS:
        path = PROJECT_ROOT / folder

        if path.is_dir():
            print(f"[OK]      {folder}/")
        else:
            print(f"[MISSING] {folder}/")
            missing_folders.append(folder)

    print("\nScanning for dataset files...")
    dataset_files = []

    for path in (PROJECT_ROOT / "data").rglob("*"):
        if path.is_file() and path.suffix.lower() in DATA_EXTENSIONS:
            dataset_files.append({
                "path": str(path.relative_to(PROJECT_ROOT)),
                "extension": path.suffix.lower(),
                "size_bytes": path.stat().st_size,
            })

    if dataset_files:
        for item in dataset_files:
            print(
                f"[DATA] {item['path']} "
                f"({item['size_bytes']:,} bytes)"
            )
    else:
        print("[INFO] No dataset files found yet. This is normal.")

    report = {
        "project": "AURIS-X",
        "audit_time": datetime.now().astimezone().isoformat(),
        "project_root": str(PROJECT_ROOT),
        "missing_folders": missing_folders,
        "dataset_file_count": len(dataset_files),
        "dataset_files": dataset_files,
    }

    report_path = PROJECT_ROOT / "reports" / "workspace_audit.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print(f"\nReport saved to: {report_path}")
    print(f"Dataset files found: {len(dataset_files)}")

    if missing_folders:
        print("Result: Some expected folders are missing.")
    else:
        print("Result: Workspace structure looks good.")

    print("=" * 60)


if __name__ == "__main__":
    main()
