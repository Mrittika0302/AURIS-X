
from pathlib import Path
import json

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parent.parent
RASTER = ROOT / "data" / "population" / "coimbatore_population_2026_approx.tif"
REPORT = ROOT / "reports" / "population_subset_validation.json"


def main():
    if not RASTER.exists():
        raise FileNotFoundError(f"Raster not found: {RASTER}")

    with rasterio.open(RASTER) as src:
        data = src.read(1, masked=True)
        values = data.compressed()

        if values.size == 0:
            raise ValueError("The raster contains no valid pixels.")

        if not np.isfinite(values).all():
            raise ValueError("Valid raster values contain NaN or infinity.")

        if (values < 0).any():
            raise ValueError("Valid raster values contain negative values.")

        bounds = src.bounds
        report = {
            "file": str(RASTER),
            "crs": str(src.crs),
            "width": src.width,
            "height": src.height,
            "pixel_size_degrees": list(src.res),
            "bounds": {
                "left": bounds.left,
                "bottom": bounds.bottom,
                "right": bounds.right,
                "top": bounds.top,
            },
            "valid_pixels": int(values.size),
            "zero_value_pixels": int((values == 0).sum()),
            "positive_value_pixels": int((values > 0).sum()),
            "minimum": float(values.min()),
            "median": float(np.median(values)),
            "p90": float(np.percentile(values, 90)),
            "p99": float(np.percentile(values, 99)),
            "maximum": float(values.max()),
            "mean": float(values.mean()),
            "sum_of_valid_values": float(values.sum(dtype=np.float64)),
            "negative_values": int((values < 0).sum()),
            "interpretation": (
                "Structural checks only. Confirm WorldPop product units and "
                "documentation before interpreting sums as population totals. "
                "The study extent is an approximate rectangle, not an official boundary."
            ),
        }

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("POPULATION SUBSET VALIDATION COMPLETE")
    print(json.dumps(report, indent=2))
    print(f"\nReport saved to: {REPORT}")


if __name__ == "__main__":
    main()
