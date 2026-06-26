"""Modelling validations: cross-validation routines and the validation registry."""

import kotsu.registration
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold

_TARGET = "cui_risk_score"


class KFoldCV:
    """K-fold cross-validation callable.

    Instantiated with dataset/split configuration; called with a model instance to
    run the validation and return averaged metrics.

    This class is used as the validation entry_point in kotsu's ValidationRegistry:
    ``make()`` calls ``KFoldCV(dataset_path=..., n_splits=...)`` which returns a
    callable, and kotsu's run loop then calls ``instance(model)`` to obtain results.

    Args:
        dataset_path: Path to the CSV dataset file.
        n_splits: Number of K-fold splits. Defaults to 5.
    """

    def __init__(self, *, dataset_path: str, n_splits: int = 5) -> None:
        self.dataset_path = dataset_path
        self.n_splits = n_splits

    def __call__(self, model) -> dict[str, float]:
        """Run K-fold CV and return averaged metrics.

        Args:
            model: A fitted or unfitted model instance with ``fit(train_df)`` and
                ``predict(input_df)`` methods.

        Returns:
            Dict with keys ``mae``, ``rmse``, and ``r2`` — each averaged over folds.
        """
        dataset_df = pd.read_csv(self.dataset_path)
        all_columns = model.feature_columns + [_TARGET]
        clean_df = dataset_df[all_columns].dropna()

        kf = KFold(n_splits=self.n_splits, shuffle=True, random_state=42)
        indices = np.arange(len(clean_df))

        mae_scores: list[float] = []
        rmse_scores: list[float] = []
        r2_scores: list[float] = []

        for train_idx, test_idx in kf.split(indices):
            train_df = clean_df.iloc[train_idx]
            test_df = clean_df.iloc[test_idx]

            model.fit(train_df)
            predictions = model.predict(test_df)
            actuals = test_df[_TARGET].to_numpy()

            mae_scores.append(mean_absolute_error(actuals, predictions))
            rmse_scores.append(np.sqrt(mean_squared_error(actuals, predictions)))
            r2_scores.append(r2_score(actuals, predictions))

        return {
            "mae": float(np.mean(mae_scores)),
            "rmse": float(np.mean(rmse_scores)),
            "r2": float(np.mean(r2_scores)),
        }


validation_registry = kotsu.registration.ValidationRegistry()
validation_registry.register(
    id="kfold-5-v1.0",
    entry_point=KFoldCV,
    kwargs={
        "dataset_path": "data/datasets/baseline_1k.csv",
        "n_splits": 5,
    },
)
