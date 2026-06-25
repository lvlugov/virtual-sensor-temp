"""Tests for lean_virtual_sensor.dataset.pipeline."""


import pytest
from lean_virtual_sensor.dataset.configs import DatasetConfig
from lean_virtual_sensor.dataset.pipeline import run_dataset_pipeline


@pytest.fixture()
def gen_config_yaml(tmp_path):
    """Write a minimal generation_config.yaml and return its path."""
    yaml_content = (
        "run:\n"
        '  reference_date: "2026-01-01"\n'
        "  random_seed: 42\n"
        "temperature_series:\n"
        "  window_days: 90\n"
    )
    config_path = tmp_path / "generation_config.yaml"
    config_path.write_text(yaml_content)
    return config_path


def test_run_dataset_pipeline_path_resolution(tmp_path, gen_config_yaml, monkeypatch):
    """Pipeline passes correct paths to each step and skips steps whose output exists."""
    data_dir = tmp_path / "data"
    config = DatasetConfig(
        name="test_ds",
        generation_config_path=gen_config_yaml,
        # Non-existent weather_dir causes step 2 (gen_timeseries) to be skipped.
        weather_dir=tmp_path / "no_weather",
        llm_config={"seed": 1},
    )

    expected_raw_csv = data_dir / "raw_synthetic_inputs" / "test_ds.csv"
    expected_featurised_csv = data_dir / "featurised" / "test_ds.csv"
    expected_final_csv = data_dir / "datasets" / "test_ds.csv"

    generate_calls: list[dict] = []
    featurise_calls: list[dict] = []
    llm_calls: list[dict] = []

    def mock_run_pipeline(config_path, *, output_path_override=None, write_output=True):
        generate_calls.append(
            {"config_path": config_path, "output_path_override": output_path_override}
        )
        if output_path_override is not None:
            output_path_override.parent.mkdir(parents=True, exist_ok=True)
            output_path_override.write_text("generated")
        return True

    def mock_featurise_inventory(
        raw_csv, timeseries_dir, weather_dir, output_csv, *, reference_date, seed
    ):
        featurise_calls.append({"raw_csv": raw_csv, "output_csv": output_csv})
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        output_csv.write_text("featurised")
        return output_csv

    def mock_score_dataset(featurised_csv, output_csv, *, llm_config):
        llm_calls.append({"featurised_csv": featurised_csv, "output_csv": output_csv})
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        output_csv.write_text("scored")
        return output_csv

    monkeypatch.setattr("lean_virtual_sensor.dataset.pipeline.run_pipeline", mock_run_pipeline)
    monkeypatch.setattr(
        "lean_virtual_sensor.dataset.pipeline.featurise_inventory", mock_featurise_inventory
    )
    monkeypatch.setattr("lean_virtual_sensor.dataset.pipeline.score_dataset", mock_score_dataset)

    result = run_dataset_pipeline(config, data_dir=data_dir)

    assert result == expected_final_csv

    assert len(generate_calls) == 1
    assert generate_calls[0]["output_path_override"] == expected_raw_csv

    assert len(featurise_calls) == 1
    assert featurise_calls[0]["raw_csv"] == expected_raw_csv
    assert featurise_calls[0]["output_csv"] == expected_featurised_csv

    assert len(llm_calls) == 1
    assert llm_calls[0]["featurised_csv"] == expected_featurised_csv
    assert llm_calls[0]["output_csv"] == expected_final_csv

    # Skip-if-exists: re-running with all outputs present must not invoke any step.
    generate_calls.clear()
    featurise_calls.clear()
    llm_calls.clear()

    result2 = run_dataset_pipeline(config, data_dir=data_dir)

    assert result2 == expected_final_csv
    assert len(generate_calls) == 0
    assert len(featurise_calls) == 0
    assert len(llm_calls) == 0

    # raw_synthetic_inputs_name / featurised_name default to config.name.
    assert expected_raw_csv.name == f"{config.name}.csv"
    assert expected_featurised_csv.name == f"{config.name}.csv"
