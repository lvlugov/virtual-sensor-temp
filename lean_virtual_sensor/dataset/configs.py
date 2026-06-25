from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class DatasetConfig:
    """Configuration for a single dataset pipeline run.

    Attributes:
        name: Unique identifier; used as default for output file/dir names.
        generation_config_path: Path to the generation_config.yaml.
        weather_dir: Pre-existing weather cache directory; timeseries step is skipped if absent.
        llm_config: Passed through to the LLM scoring step.
        raw_synthetic_inputs_name: Stem for data/raw_synthetic_inputs/{name}.csv.
            Defaults to ``name``.
        timeseries_name: Subdirectory name for data/timeseries/{name}/.
            Defaults to ``name``.
        featurised_name: Stem for data/featurised/{name}.csv.
            Defaults to ``name``.
    """

    name: str
    generation_config_path: Path
    weather_dir: Path
    llm_config: dict = field(default_factory=dict)
    raw_synthetic_inputs_name: str | None = None
    timeseries_name: str | None = None
    featurised_name: str | None = None


BASELINE_1K = DatasetConfig(
    name="baseline_1k",
    generation_config_path=Path(
        "lean_virtual_sensor/inputs_generation/config/generation_config.yaml"
    ),
    weather_dir=Path("lean_virtual_sensor/output"),
    llm_config={"seed": 42},
)

BASELINE_1K_LLM = DatasetConfig(
    name="baseline_1k_llm",
    generation_config_path=BASELINE_1K.generation_config_path,
    weather_dir=BASELINE_1K.weather_dir,
    llm_config={"seed": 99},
    featurised_name="baseline_1k",
)

ALL_CONFIGS: dict[str, DatasetConfig] = {
    "baseline_1k": BASELINE_1K,
    "baseline_1k_llm": BASELINE_1K_LLM,
}
