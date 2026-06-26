"""Tests for lean_virtual_sensor.dataset.llm_scoring."""

import numpy as np
import pandas as pd
import pytest
from lean_virtual_sensor.dataset.llm_scoring import score_dataset


@pytest.fixture()
def featurised_csv(tmp_path):
    """Write a 5-row featurised CSV and return its path."""
    featurised_df = pd.DataFrame(
        {
            "Asset": ["A-001", "A-002", "A-003", "A-004", "A-005"],
            "ach_90d": [120.0, 85.0, 200.0, 55.0, 310.0],
            "wet_load": [0.12, 0.34, 0.08, 0.55, 0.21],
        }
    )
    csv_path = tmp_path / "featurised.csv"
    featurised_df.to_csv(csv_path, index=False)
    return csv_path


def test_score_dataset_mock(featurised_csv, tmp_path):
    """score_dataset writes all rows with cui_risk_score in [0, 100]."""
    output_csv = tmp_path / "scored.csv"
    result_path = score_dataset(featurised_csv, output_csv, llm_config={"seed": 42})

    assert result_path == output_csv
    scored_df = pd.read_csv(result_path)

    assert "cui_risk_score" in scored_df.columns
    assert len(scored_df) == 5
    for score in scored_df["cui_risk_score"]:
        assert isinstance(int(score), int)
        assert 0 <= int(score) <= 100


def test_score_dataset_resume(featurised_csv, tmp_path):
    """score_dataset preserves already-scored rows and fills in the rest."""
    featurised_df = pd.read_csv(featurised_csv)
    partial_df = featurised_df.copy()
    partial_df["cui_risk_score"] = [77.0, 88.0, np.nan, np.nan, np.nan]

    output_csv = tmp_path / "scored.csv"
    partial_df.to_csv(output_csv, index=False)

    score_dataset(featurised_csv, output_csv, llm_config={"seed": 42})
    result_df = pd.read_csv(output_csv)

    assert result_df.loc[result_df["Asset"] == "A-001", "cui_risk_score"].iloc[0] == 77
    assert result_df.loc[result_df["Asset"] == "A-002", "cui_risk_score"].iloc[0] == 88

    for asset in ["A-003", "A-004", "A-005"]:
        score = result_df.loc[result_df["Asset"] == asset, "cui_risk_score"].iloc[0]
        assert 0 <= int(score) <= 100
