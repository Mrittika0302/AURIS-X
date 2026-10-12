
from pathlib import Path
import json
import numpy as np
import rasterio

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RASTER_PATH = (
    PROJECT_ROOT
    / "data"
    / "population"
    / "ind_pop_2026_CN_100m_R2025A_v1.tif"
)
REPORT_PATH = PROJECT_ROOT / "reports" / "population_raster_inspection.json"


def main():
    if not RASTER_PATH.exists():
        raise FileNotFoundError(f"Population raster not found: {RASTER_PATH}")

    with rasterio.open(RASTER_PATH) as src:
        values = src.read(1, masked=True)
        valid = values.compressed()

        report = {
            "file": str(RASTER_PATH),
            "driver": src.driver,
            "width_pixels": src.width,
            "height_pixels": src.height,
            "band_count": src.count,
            "coordinate_reference_system": str(src.crs),
            "bounds": {
                "left": src.bounds.left,
                "bottom": src.bounds.bottom,
                "right": src.bounds.right,
                "top": src.bounds.top,
            },
            "pixel_size": list(src.res),
            "nodata_value": src.nodata,
            "data_type": src.dtypes[0],
            "valid_pixel_count": int(valid.size),
            "minimum_valid_value": float(valid.min()) if valid.size else None,
            "maximum_valid_value": float(valid.max()) if valid.size else None,
            "mean_valid_value": float(valid.mean()) if valid.size else None,
            "negative_valid_pixel_count": int((valid < 0).sum()),
            "description": src.descriptions[0],
            "interpretation": (
                "Inspect metadata before using values. Confirm the raster's "
                "geographic coverage, units, nodata handling and licensing. "
                "WorldPop values are modelled estimates, not direct counts."
            ),
        }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("POPULATION RASTER INSPECTION COMPLETE")
    print(json.dumps(report, indent=2))
    print(f"\nReport saved to: {REPORT_PATH}")


if __name__ == "__main__":
    main()
