"""Mock LLM scorer that assigns random CUI risk scores to a featurised dataset.

The mock implementation is seeded for reproducibility. Real LLM call stubs
(_build_prompt, _call_llm) are present for future implementation.
"""

from __future__ import annotations

import random
from pathlib import Path

import pandas as pd


def score_dataset(featurised_csv: Path, output_csv: Path, *, llm_config: dict) -> Path:
    """Append cui_risk_score column (int 0-100) to featurised CSV.

    Mock implementation: random scores seeded from llm_config.get("seed", 42).
    Resume: if output_csv exists with partial scores, skips already-scored rows.

    The RNG is always advanced once per row (including already-scored rows), so
    unscored rows receive the same value regardless of how many were pre-scored.

    Args:
        featurised_csv: Input CSV with featurised asset rows.
        output_csv: Destination CSV with appended cui_risk_score column.
        llm_config: Config dict; "seed" key controls random score generation.

    Returns:
        Path to the written output CSV.
    """
    seed = llm_config.get("seed", 42)
    featurised_df = pd.read_csv(featurised_csv)

    partial_df: pd.DataFrame | None = None
    already_scored_ids: set[str] = set()
    if output_csv.exists():
        partial_df = pd.read_csv(output_csv)
        if "cui_risk_score" in partial_df.columns:
            scored_mask = partial_df["cui_risk_score"].notna()
            already_scored_ids = set(partial_df.loc[scored_mask, "Asset"].astype(str))

    rng = random.Random(seed)
    scores: list[int] = []
    for _, row in featurised_df.iterrows():
        generated = rng.randint(0, 100)
        asset_id = str(row["Asset"])
        if asset_id in already_scored_ids and partial_df is not None:
            existing_rows = partial_df[partial_df["Asset"].astype(str) == asset_id]
            scores.append(int(existing_rows["cui_risk_score"].iloc[0]))
        else:
            scores.append(generated)

    scored_df = featurised_df.copy()
    scored_df["cui_risk_score"] = scores

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    scored_df.to_csv(output_csv, index=False)
    return output_csv


def _build_prompt(asset_row: dict) -> str:
    """Format one asset's features into a scoring prompt."""
    raise NotImplementedError


def _call_llm(prompt: str, *, llm_config: dict) -> int:
    """Call LLM API, parse response, return integer 0-100."""
    raise NotImplementedError
