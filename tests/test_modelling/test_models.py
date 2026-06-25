"""Tests for lean_virtual_sensor.modelling.models."""

import numpy as np
import pandas as pd
from lean_virtual_sensor.modelling.models import SklearnModel
from sklearn.linear_model import LinearRegression


def _make_toy_df(n_rows: int = 20) -> pd.DataFrame:
    """Return a tiny DataFrame with three numeric features and a target column."""
    rng = np.random.default_rng(seed=0)
    return pd.DataFrame(
        {
            "feature_a": rng.uniform(0.0, 10.0, size=n_rows),
            "feature_b": rng.uniform(0.0, 5.0, size=n_rows),
            "feature_c": rng.integers(0, 100, size=n_rows).astype(float),
            "cui_risk_score": rng.integers(0, 100, size=n_rows),
        }
    )


def test_sklearn_model_fit_predict():
    """SklearnModel wraps a LinearRegression and returns float predictions of correct shape."""
    toy_df = _make_toy_df(n_rows=20)
    feature_cols = ["feature_a", "feature_b", "feature_c"]

    model = SklearnModel(
        estimator=LinearRegression(),
        feature_columns=feature_cols,
        target="cui_risk_score",
    )

    model.fit(toy_df)
    predictions = model.predict(toy_df)

    assert predictions.shape == (20,), f"Expected shape (20,), got {predictions.shape}"
    assert np.issubdtype(predictions.dtype, np.floating), (
        f"Expected float dtype, got {predictions.dtype}"
    )
