"""Modelling models: sklearn wrappers and the model registry."""

import kotsu.registration
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

# Feature columns drawn from the baseline dataset (all numeric, zero nulls).
_FEATURE_COLUMNS: list[str] = [
    "component_diameter",
    "furnished_thickness",
    "insulation_thickness",
    "operating_temperature",
    "min_operating_temperature",
    "max_operating_temperature",
    "avg_cycles_per_quarter",
    "operation_vs_shutdown_fraction",
    "last_inspection_thickness",
    "washdown_records",
    "coating_age_years",
    "system_age_years",
    "ach_90d",
    "cycle_count",
    "wet_load",
    "api583_total_score",
]


class SklearnModel:
    """Thin wrapper so sklearn estimators have fit/predict against DataFrames.

    Args:
        estimator: A scikit-learn estimator instance (must implement fit/predict).
        feature_columns: Column names to use as model features.
        target: Name of the target column. Defaults to "cui_risk_score".
    """

    def __init__(
        self,
        estimator,
        feature_columns: list[str],
        target: str = "cui_risk_score",
    ) -> None:
        self.estimator = estimator
        self.feature_columns = feature_columns
        self.target = target

    def fit(self, train_df: pd.DataFrame) -> None:
        """Fit the estimator on train_df.

        Args:
            train_df: DataFrame containing feature columns and the target column.
        """
        feature_matrix = train_df[self.feature_columns].to_numpy()
        target_vector = train_df[self.target].to_numpy()
        self.estimator.fit(feature_matrix, target_vector)

    def predict(self, input_df: pd.DataFrame) -> np.ndarray:
        """Generate predictions for input_df.

        Args:
            input_df: DataFrame containing feature columns.

        Returns:
            1-D array of predictions with shape (n_rows,).
        """
        feature_matrix = input_df[self.feature_columns].to_numpy()
        return self.estimator.predict(feature_matrix)


model_registry = kotsu.registration.ModelRegistry()
model_registry.register(
    id="linear-v1.0",
    entry_point=SklearnModel,
    kwargs={
        "estimator": LinearRegression(),
        "feature_columns": _FEATURE_COLUMNS,
    },
)
