"""Entry point for running modelling experiments via kotsu."""


import kotsu.run
import pandas as pd

from lean_virtual_sensor.modelling.models import model_registry
from lean_virtual_sensor.modelling.validations import validation_registry


def run_experiments(
    results_path: str = "data/results/results.csv",
    force_rerun: str | list[str] | None = None,
) -> pd.DataFrame:
    """Run all registered models through all registered validations.

    Results are written to ``results_path`` (CSV) and returned as a DataFrame.
    Skips model-validation combinations that already have results unless
    ``force_rerun`` is specified.

    Args:
        results_path: File path to write results CSV to and read prior results from.
        force_rerun: Controls which models are re-evaluated.
            - ``None`` — only run combinations with no prior result (default).
            - ``"all"`` — rerun everything.
            - list of model IDs — rerun only those models.

    Returns:
        DataFrame of validation results (one row per model-validation combination).
    """
    return kotsu.run.run(
        model_registry=model_registry,
        validation_registry=validation_registry,
        results_path=results_path,
        force_rerun=force_rerun,
    )
