
from pathlib import Path
import json
import math
import webbrowser

import pandas as pd
import folium
from folium.plugins import FastMarkerCluster


# ============================================================
# AURIS-X: HEALTHCARE ACCESSIBILITY MAP
# Study area: approximate Coimbatore bounding box
# Output: reports/healthcare_accessibility_map.html
# No external map tiles are used.
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

ACCESS_FILE = (
    ROOT / "data" / "gold"
    / "healthcare_accessibility_by_population_cell.csv"
)

FACILITY_FILE = (
    ROOT / "data" / "silver"
    / "healthcare_network_matches_20261011_122708.csv"
)

SUMMARY_FILE = (
    ROOT / "reports"
    / "healthcare_accessibility_summary.json"
)

OUTPUT_FILE = (
    ROOT / "reports"
    / "healthcare_accessibility_map.html"
)

# Map performance: maximum number of population cells rendered.
# Set to None to render every cell, but the HTML may become very large.
MAX_POPULATION_POINTS = 25000

# Screening thresholds, not official healthcare-access standards.
UNDERSERVED_THRESHOLD_M = 5000

# Approximate study extent, not an official municipal boundary.
CENTER_LAT = 11.00
CENTER_LON = 77.00
INITIAL_ZOOM = 11


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def require_file(path):
    if not path.exists():
        raise FileNotFoundError(
            f"Required input file not found:\n{path}\n"
            "Check the filename and confirm the previous pipeline "
            "steps completed successfully."
        )


def safe_number(value):
    try:
        number = float(value)
        if math.isfinite(number):
            return number
    except (TypeError, ValueError):
        pass
    return None


def truthy(value):
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {
        "true", "1", "yes", "y"
    }


def format_distance(value):
    number = safe_number(value)
    if number is None:
        return "Unavailable"
    return f"{number / 1000:.2f} km"


def distance_band(value, reachable):
    if not reachable:
        return "Unreachable"

    distance = safe_number(value)
    if distance is None:
        return "Unreachable"

    if distance <= 3000:
        return "Within 3 km"
    if distance <= 5000:
        return "Over 3 to 5 km"
    if distance <= 10000:
        return "Over 5 to 10 km"
    return "Over 10 km"


def distance_color(band):
    return {
        "Within 3 km": "#238b45",
        "Over 3 to 5 km": "#a1d99b",
        "Over 5 to 10 km": "#feb24c",
        "Over 10 km": "#e31a1c",
        "Unreachable": "#54278f",
    }.get(band, "#808080")


def html_escape(value):
    """Escape text before inserting it into popup HTML."""
    text = str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


# ------------------------------------------------------------
# Load inputs
# ------------------------------------------------------------

require_file(ACCESS_FILE)
require_file(FACILITY_FILE)

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

print("Loading accessibility results...")
access = pd.read_csv(ACCESS_FILE, low_memory=False)

print("Loading healthcare facility network matches...")
facilities = pd.read_csv(FACILITY_FILE, low_memory=False)

required_access_columns = {
    "latitude",
    "longitude",
    "population_raster_value",
    "driving_distance_m",
    "driving_reachable",
    "walking_distance_m",
    "walking_reachable",
    "drive_snap_distance_m",
    "walk_snap_distance_m",
}

missing = required_access_columns - set(access.columns)
if missing:
    raise ValueError(
        "Accessibility CSV is missing required columns: "
        + ", ".join(sorted(missing))
    )

required_facility_columns = {
    "latitude",
    "longitude",
    "name",
    "category",
}

missing = required_facility_columns - set(facilities.columns)
if missing:
    raise ValueError(
        "Facility CSV is missing required columns: "
        + ", ".join(sorted(missing))
    )

# Convert coordinate and distance fields to numeric values.
numeric_access_columns = [
    "latitude",
    "longitude",
    "population_raster_value",
    "driving_distance_m",
    "walking_distance_m",
    "drive_snap_distance_m",
    "walk_snap_distance_m",
]

for column in numeric_access_columns:
    access[column] = pd.to_numeric(
        access[column], errors="coerce"
    )

facilities["latitude"] = pd.to_numeric(
    facilities["latitude"], errors="coerce"
)
facilities["longitude"] = pd.to_numeric(
    facilities["longitude"], errors="coerce"
)

# Keep records with usable coordinates.
access = access.dropna(subset=["latitude", "longitude"]).copy()
facilities = facilities.dropna(
    subset=["latitude", "longitude"]
).copy()

# Interpret reachability as explicit boolean values.
access["driving_reachable"] = access[
    "driving_reachable"
].map(truthy)

access["walking_reachable"] = access[
    "walking_reachable"
].map(truthy)

# A distance is not considered accessible if the pipeline says
# the cell is unreachable.
access["driving_band"] = access.apply(
    lambda row: distance_band(
        row["driving_distance_m"],
        row["driving_reachable"],
    ),
    axis=1,
)

access["walking_band"] = access.apply(
    lambda row: distance_band(
        row["walking_distance_m"],
        row["walking_reachable"],
    ),
    axis=1,
)

access["over_5km_both_modes"] = (
    access["driving_reachable"]
    & access["walking_reachable"]
    & (access["driving_distance_m"] > UNDERSERVED_THRESHOLD_M)
    & (access["walking_distance_m"] > UNDERSERVED_THRESHOLD_M)
)

access["unreachable_both_modes"] = (
    ~access["driving_reachable"]
    & ~access["walking_reachable"]
)

access["drive_snap_review"] = (
    access["drive_snap_distance_m"] > 100
)

access["walk_snap_review"] = (
    access["walk_snap_distance_m"] > 100
)

access["any_snap_review"] = (
    access["drive_snap_review"]
    | access["walk_snap_review"]
)


# ------------------------------------------------------------
# Calculate summary statistics from the current CSV
# ------------------------------------------------------------

total_cells = len(access)

drive_reachable = int(access["driving_reachable"].sum())
walk_reachable = int(access["walking_reachable"].sum())

drive_unreachable = total_cells - drive_reachable
walk_unreachable = total_cells - walk_reachable

both_over_5km = int(access["over_5km_both_modes"].sum())
both_unreachable = int(access["unreachable_both_modes"].sum())

drive_snap_review = int(access["drive_snap_review"].sum())
walk_snap_review = int(access["walk_snap_review"].sum())
any_snap_review = int(access["any_snap_review"].sum())


def percentile_km(series, percentile):
    valid = pd.to_numeric(series, errors="coerce").dropna()
    if valid.empty:
        return None
    return round(float(valid.quantile(percentile)) / 1000, 3)


computed_summary = {
    "population_cells_with_coordinates": total_cells,
    "healthcare_facility_records_with_coordinates": len(facilities),
    "driving_reachable_cells": drive_reachable,
    "driving_unreachable_cells": drive_unreachable,
    "driving_reachable_percent": round(
        drive_reachable / total_cells * 100, 2
    ) if total_cells else None,
    "walking_reachable_cells": walk_reachable,
    "walking_unreachable_cells": walk_unreachable,
    "walking_reachable_percent": round(
        walk_reachable / total_cells * 100, 2
    ) if total_cells else None,
    "over_5km_in_both_modes_cells": both_over_5km,
    "unreachable_in_both_modes_cells": both_unreachable,
    "drive_snap_over_100m_cells": drive_snap_review,
    "walk_snap_over_100m_cells": walk_snap_review,
    "any_snap_over_100m_cells": any_snap_review,
    "driving_median_distance_km": percentile_km(
        access.loc[access["driving_reachable"], "driving_distance_m"],
        0.5,
    ),
    "driving_p90_distance_km": percentile_km(
        access.loc[access["driving_reachable"], "driving_distance_m"],
        0.9,
    ),
    "walking_median_distance_km": percentile_km(
        access.loc[access["walking_reachable"], "walking_distance_m"],
        0.5,
    ),
    "walking_p90_distance_km": percentile_km(
        access.loc[access["walking_reachable"], "walking_distance_m"],
        0.9,
    ),
}

if SUMMARY_FILE.exists():
    try:
        with SUMMARY_FILE.open("r", encoding="utf-8") as file:
            previous_summary = json.load(file)
        print("Existing summary JSON found; map statistics are recalculated")
        print("from the accessibility CSV for consistency.")
    except (json.JSONDecodeError, OSError):
        pass


# ------------------------------------------------------------
# Create a tile-free interactive map
# ------------------------------------------------------------

print("Building map...")
m = folium.Map(
    location=[CENTER_LAT, CENTER_LON],
    zoom_start=INITIAL_ZOOM,
    tiles=None,
    control_scale=True,
)

# A neutral background is intentional: there are no external tiles.
folium.Rectangle(
    bounds=[[10.85, 76.85], [11.15, 77.15]],
    color="#666666",
    weight=1,
    fill=False,
    tooltip="Approximate study extent — not an official boundary",
).add_to(m)


# ------------------------------------------------------------
# Population-cell layer
# ------------------------------------------------------------

driving_group = folium.FeatureGroup(
    name="Driving accessibility",
    show=True,
)

walking_group = folium.FeatureGroup(
    name="Walking accessibility",
    show=False,
)

underserved_group = folium.FeatureGroup(
    name="Over 5 km in both modes",
    show=True,
)

unreachable_group = folium.FeatureGroup(
    name="Unreachable in both modes",
    show=False,
)

snap_group = folium.FeatureGroup(
    name="Snap review flags (>100 m)",
    show=False,
)

# Deterministic sampling keeps the HTML more manageable.
if (
    MAX_POPULATION_POINTS is not None
    and len(access) > MAX_POPULATION_POINTS
):
    map_access = access.sample(
        n=MAX_POPULATION_POINTS,
        random_state=42,
    ).copy()
    sampled = True
else:
    map_access = access.copy()
    sampled = False

print(
    f"Rendering {len(map_access):,} of "
    f"{len(access):,} population cells."
)

for row in map_access.itertuples(index=False):
    lat = safe_number(getattr(row, "latitude", None))
    lon = safe_number(getattr(row, "longitude", None))

    if lat is None or lon is None:
        continue

    drive_band = getattr(row, "driving_band", "Unreachable")
    walk_band = getattr(row, "walking_band", "Unreachable")

    drive_distance = safe_number(
        getattr(row, "driving_distance_m", None)
    )
    walk_distance = safe_number(
        getattr(row, "walking_distance_m", None)
    )

    drive_ok = bool(getattr(row, "driving_reachable", False))
    walk_ok = bool(getattr(row, "walking_reachable", False))

    pop_value = safe_number(
        getattr(row, "population_raster_value", None)
    )

    population_label = (
        f"{pop_value:.3f}" if pop_value is not None else "Unavailable"
    )

    cell_id = getattr(row, "population_cell_id", "Not recorded")

    popup = (
        f"<b>Population cell:</b> {html_escape(cell_id)}<br>"
        f"<b>Raster value:</b> {population_label}"
        " (units not verified)<br>"
        f"<b>Driving:</b> {html_escape(drive_band)}"
        f" — {format_distance(drive_distance)}<br>"
        f"<b>Walking:</b> {html_escape(walk_band)}"
        f" — {format_distance(walk_distance)}<br>"
        f"<b>Driving reachable:</b> {'Yes' if drive_ok else 'No'}<br>"
        f"<b>Walking reachable:</b> {'Yes' if walk_ok else 'No'}"
    )

    folium.CircleMarker(
        location=[lat, lon],
        radius=2,
        color=distance_color(drive_band),
        weight=0,
        fill=True,
        fill_color=distance_color(drive_band),
        fill_opacity=0.60,
        popup=folium.Popup(popup, max_width=320),
    ).add_to(driving_group)

    folium.CircleMarker(
        location=[lat, lon],
        radius=2,
        color=distance_color(walk_band),
        weight=0,
        fill=True,
        fill_color=distance_color(walk_band),
        fill_opacity=0.60,
        popup=folium.Popup(popup, max_width=320),
    ).add_to(walking_group)

    if truthy(getattr(row, "over_5km_both_modes", False)):
        folium.CircleMarker(
            location=[lat, lon],
            radius=3,
            color="#b30000",
            weight=0.5,
            fill=True,
            fill_color="#e31a1c",
            fill_opacity=0.75,
            popup=folium.Popup(popup, max_width=320),
        ).add_to(underserved_group)

    if truthy(getattr(row, "unreachable_both_modes", False)):
        folium.CircleMarker(
            location=[lat, lon],
            radius=3,
            color="#54278f",
            weight=0.5,
            fill=True,
            fill_color="#54278f",
            fill_opacity=0.85,
            popup=folium.Popup(popup, max_width=320),
        ).add_to(unreachable_group)

    if truthy(getattr(row, "any_snap_review", False)):
        drive_snap = safe_number(
            getattr(row, "drive_snap_distance_m", None)
        )
        walk_snap = safe_number(
            getattr(row, "walk_snap_distance_m", None)
        )

        snap_popup = (
            f"<b>Snap review flag</b><br>"
            f"Population cell: {html_escape(cell_id)}<br>"
            f"Driving snap distance: {format_distance(drive_snap)}<br>"
            f"Walking snap distance: {format_distance(walk_snap)}<br>"
            "A long straight-line snap distance requires review; "
            "it does not by itself prove a network error."
        )

        folium.CircleMarker(
            location=[lat, lon],
            radius=3,
            color="#252525",
            weight=1,
            fill=True,
            fill_color="#ffff00",
            fill_opacity=0.85,
            popup=folium.Popup(snap_popup, max_width=320),
        ).add_to(snap_group)


driving_group.add_to(m)
walking_group.add_to(m)
underserved_group.add_to(m)
unreachable_group.add_to(m)
snap_group.add_to(m)


# ------------------------------------------------------------
# Healthcare facility markers
# ------------------------------------------------------------

facility_group = folium.FeatureGroup(
    name="Healthcare facilities",
    show=True,
)

for row in facilities.itertuples(index=False):
    lat = safe_number(getattr(row, "latitude", None))
    lon = safe_number(getattr(row, "longitude", None))

    if lat is None or lon is None:
        continue

    name = getattr(row, "name", None)
    category = getattr(row, "category", None)

    if pd.isna(name) or not str(name).strip():
        name = "Unnamed facility"

    if pd.isna(category) or not str(category).strip():
        category = "Unclassified"

    popup_parts = [
        f"<b>{html_escape(name)}</b>",
        f"<b>Category:</b> {html_escape(category)}",
    ]

    for column, label in [
        ("osm_type", "OSM type"),
        ("osm_id", "OSM ID"),
        ("street", "Street"),
        ("city", "City"),
        ("postcode", "Postcode"),
        ("drive_snap_distance_m", "Driving snap distance"),
        ("walk_snap_distance_m", "Walking snap distance"),
    ]:
        if hasattr(row, column):
            value = getattr(row, column)
            if value is not None and not pd.isna(value):
                if "snap_distance" in column:
                    value = format_distance(value)
                popup_parts.append(
                    f"<b>{label}:</b> {html_escape(value)}"
                )

    popup_parts.append(
        "<i>Facility operation and services have not been verified.</i>"
    )

    folium.CircleMarker(
        location=[lat, lon],
        radius=5,
        color="#08519c",
        weight=1,
        fill=True,
        fill_color="#3182bd",
        fill_opacity=0.95,
        tooltip=f"{name} ({category})",
        popup=folium.Popup(
            "<br>".join(popup_parts),
            max_width=350,
        ),
    ).add_to(facility_group)

facility_group.add_to(m)


# ------------------------------------------------------------
# HTML summary panel and limitations
# ------------------------------------------------------------

def pct(part, total):
    return f"{part / total * 100:.2f}%" if total else "N/A"


def stat_line(label, value):
    return (
        "<div style='margin:4px 0;'>"
        f"<b>{html_escape(label)}:</b> {html_escape(value)}"
        "</div>"
    )


summary_html = """
<div style="
    position: fixed;
    top: 12px;
    left: 55px;
    z-index: 9999;
    width: 330px;
    max-height: 78vh;
    overflow-y: auto;
    background: white;
    padding: 12px 14px;
    border: 1px solid #777;
    border-radius: 6px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.25);
    font-family: Arial, sans-serif;
    font-size: 12px;
">
"""

summary_html += """
<div style="font-size:18px;font-weight:bold;margin-bottom:4px;">
AURIS-X
</div>
<div style="font-size:14px;font-weight:bold;margin-bottom:10px;">
Healthcare Accessibility Screening
</div>
"""

summary_html += stat_line("Population cells", f"{total_cells:,}")
summary_html += stat_line(
    "Facility records with coordinates", f"{len(facilities):,}"
)
summary_html += "<hr>"

summary_html += "<b>Driving network</b>"
summary_html += stat_line(
    "Reachable",
    f"{drive_reachable:,} ({pct(drive_reachable, total_cells)})",
)
summary_html += stat_line("Unreachable", f"{drive_unreachable:,}")
summary_html += stat_line(
    "Median distance",
    f"{computed_summary['driving_median_distance_km']} km"
    if computed_summary["driving_median_distance_km"] is not None
    else "N/A",
)
summary_html += stat_line(
    "90th percentile",
    f"{computed_summary['driving_p90_distance_km']} km"
    if computed_summary["driving_p90_distance_km"] is not None
    else "N/A",
)

summary_html += "<hr><b>Walking network</b>"
summary_html += stat_line(
    "Reachable",
    f"{walk_reachable:,} ({pct(walk_reachable, total_cells)})",
)
summary_html += stat_line("Unreachable", f"{walk_unreachable:,}")
summary_html += stat_line(
    "Median distance",
    f"{computed_summary['walking_median_distance_km']} km"
    if computed_summary["walking_median_distance_km"] is not None
    else "N/A",
)
summary_html += stat_line(
    "90th percentile",
    f"{computed_summary['walking_p90_distance_km']} km"
    if computed_summary["walking_p90_distance_km"] is not None
    else "N/A",
)

summary_html += "<hr><b>Screening flags</b>"
summary_html += stat_line(
    "Over 5 km in both modes",
    f"{both_over_5km:,} ({pct(both_over_5km, total_cells)})",
)
summary_html += stat_line(
    "Unreachable in both modes",
    f"{both_unreachable:,} ({pct(both_unreachable, total_cells)})",
)
summary_html += stat_line(
    "Driving snap >100 m",
    f"{drive_snap_review:,}",
)
summary_html += stat_line(
    "Walking snap >100 m",
    f"{walk_snap_review:,}",
)
summary_html += stat_line(
    "Either snap >100 m",
    f"{any_snap_review:,}",
)

summary_html += """
<hr>
<b>Distance legend</b>
<div style="margin:4px 0;">
<span style="color:#238b45;">&#9632;</span> Within 3 km
</div>
<div style="margin:4px 0;">
<span style="color:#a1d99b;">&#9632;</span> Over 3 to 5 km
</div>
<div style="margin:4px 0;">
<span style="color:#feb24c;">&#9632;</span> Over 5 to 10 km
</div>
<div style="margin:4px 0;">
<span style="color:#e31a1c;">&#9632;</span> Over 10 km
</div>
<div style="margin:4px 0;">
<span style="color:#54278f;">&#9632;</span> Unreachable
</div>
<hr>
<b>Important limitations</b>
<ul style="padding-left:18px;">
<li>Study extent is approximate, not an official boundary.</li>
<li>The 5 km flag is a screening threshold, not a healthcare standard.</li>
<li>Population raster values and units have not been verified.</li>
<li>Facility operation, service availability and completeness are unverified.</li>
<li>Snap distances are straight-line distances; flags require review.</li>
<li>Network distances are not travel times.</li>
<li>Road directionality, routes and the similarity between driving and walking results require validation.</li>
<li>Unreachable means unreachable in the current graph analysis, not necessarily no real-world access.</li>
</ul>
"""

if sampled:
    summary_html += (
        "<hr><b>Display sampling:</b> "
        f"{len(map_access):,} of {total_cells:,} population cells "
        "are displayed for performance. Summary statistics use all "
        "rows in the CSV."
    )
else:
    summary_html += (
        "<hr><b>Display:</b> All population cells with coordinates "
        "are included."
    )

summary_html += """
<div style="margin-top:8px;color:#555;">
Toggle layers using the control at the upper-right of the map.
</div>
</div>
"""

m.get_root().html.add_child(folium.Element(summary_html))


# ------------------------------------------------------------
# Add layer control and save
# ------------------------------------------------------------

folium.LayerControl(
    collapsed=False,
    position="topright",
).add_to(m)

# Set a default map extent around the approximate study area.
m.fit_bounds([[10.85, 76.85], [11.15, 77.15]])

m.save(str(OUTPUT_FILE))

# Save the recalculated map summary for reproducibility.
with SUMMARY_FILE.open("w", encoding="utf-8") as file:
    json.dump(
        computed_summary,
        file,
        indent=2,
        ensure_ascii=False,
    )

print("\nMap generation completed.")
print(f"HTML map: {OUTPUT_FILE}")
print(f"Summary:  {SUMMARY_FILE}")
print(f"Cells in CSV: {total_cells:,}")
print(f"Cells displayed: {len(map_access):,}")
print(f"Facilities displayed: {len(facilities):,}")

# Open the generated map in the default browser.
webbrowser.open(OUTPUT_FILE.resolve().as_uri())
