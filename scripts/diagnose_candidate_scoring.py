
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "gold" / "healthcare_candidate_sites.csv"

df = pd.read_csv(INPUT)

components = [
    "gap_score",
    "unreachable_score",
    "distance_score",
    "demand_proxy_score",
    "snap_review_score",
]

weights = {
    "gap_score": 0.40,
    "unreachable_score": 0.20,
    "distance_score": 0.25,
    "demand_proxy_score": 0.10,
    "snap_review_score": 0.05,
}

print("=" * 72)
print("AURIS-X CANDIDATE SCORING DIAGNOSTIC")
print("Read-only: existing candidate CSV will not be modified.")
print("=" * 72)

print(f"\nInput rows: {len(df)}")
print(f"Unique candidate IDs: {df['candidate_zone_id'].nunique()}")
print(f"Duplicate candidate IDs: {df['candidate_zone_id'].duplicated().sum()}")

print("\nCOMPONENT VARIATION")
for col in components:
    s = df[col]
    print(
        f"{col:24s} unique={s.nunique():3d} "
        f"min={s.min():8.3f} max={s.max():8.3f} "
        f"mean={s.mean():8.3f} "
        f"at_100={(s == 100).sum():3d} "
        f"at_0={(s == 0).sum():3d}"
    )

print("\nTOP-10 SCORE CONTRIBUTIONS")
top = df.head(10).copy()

for col, weight in weights.items():
    top[f"{col}_contribution"] = top[col] * weight

contribution_cols = [
    f"{col}_contribution" for col in components
]
top["reconstructed_score"] = top[contribution_cols].sum(axis=1)

print(
    top[
        ["rank", "candidate_zone_id", "screening_score"]
        + contribution_cols
        + ["reconstructed_score"]
    ].to_string(index=False)
)

print("\nRANKING COMPARISON")
df["distance_only_rank"] = (
    df["mean_driving_distance_m"]
    .rank(method="min", ascending=False)
    .astype(int)
)

df["current_rank_numeric"] = df["rank"]

print(
    "Spearman correlation between current rank and distance-only rank:",
    round(
        df["current_rank_numeric"].corr(
            df["distance_only_rank"], method="spearman"
        ),
        4,
    ),
)

print("\nTOP-10 OVERLAP")
current_top10 = set(df.nsmallest(10, "rank")["candidate_zone_id"])
distance_top10 = set(
    df.nlargest(10, "mean_driving_distance_m")["candidate_zone_id"]
)

print(f"Shared candidates: {len(current_top10 & distance_top10)} of 10")
print("Distance-only top 10:")
print(
    df.nlargest(10, "mean_driving_distance_m")[
        [
            "candidate_zone_id",
            "rank",
            "mean_driving_distance_m",
            "screening_score",
        ]
    ].to_string(index=False)
)

print("\nSPATIAL CONCENTRATION")
print("Top-10 zone rows:", sorted(df.nsmallest(10, "rank")["zone_row"].tolist()))
print("Top-10 zone columns:", sorted(df.nsmallest(10, "rank")["zone_col"].tolist()))

print("\nNOTE")
print(
    "Distance-only ranking is a diagnostic comparison, not a replacement "
    "for the current score or a measure of incremental public benefit."
)
