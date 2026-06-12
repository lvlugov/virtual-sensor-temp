"""
temperature_series_driver.py
============================
Runs the full temperature_series chain for ONE asset.

``generate_asset_series`` is the single entry point: the caller passes every
static field explicitly plus that asset's ambient series (a ``datetime, temp``
DataFrame) and the config block, and gets back a
``datetime, process_temperature_c`` DataFrame on the same hourly grid as the
ambient. The caller owns everything around it — loading the static dataset,
sourcing each asset's ambient, looping the population, and writing files.

See docs/temperature_series_explained.md for the full methodology.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from temperature_series import (
    add_running_noise,
    apply_thermal_lag,
    build_target_series,
    clamp_series,
    compute_tau,
    cooldown_reference,
    place_cycles,
    size_cycles,
)


def generate_asset_series(
    *,
    operating_temperature: float,
    min_operating_temperature: float,
    max_operating_temperature: float,
    avg_cycles_per_quarter: int,
    operation_vs_shutdown_fraction: float,
    outer_diameter_mm: float,
    wall_thickness_mm: float,
    insulation_thickness_mm: float,
    insulation_material: str,
    metallurgy_family: str,
    ambient: pd.DataFrame,
    config: dict[str, Any],
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Run the full chain for one asset; return ``datetime, process_temperature_c``.

    Every static field is passed explicitly (no bundled row). ``ambient`` is a
    DataFrame with ``datetime`` and ``temp`` columns covering at least the 90-day
    window; its **last ``window_hours`` hourly rows** are used and their
    timestamps are carried through to the output unchanged. ``config`` is the
    ``temperature_series`` block (resolves ``insulation_material`` -> k and
    ``metallurgy_family`` -> rho/c). ``rng`` is used only by the noise step.

    Recovery is asymmetric: the hours returning to operating temperature
    (``target == op``) use ``tau * recovery_tau_factor`` (faster), while the
    cooldown/warm-up excursion keeps the full tau.

    Args:
        operating_temperature: Running baseline (°C).
        min_operating_temperature: Lower clamp / wide-swing target (°C).
        max_operating_temperature: Upper clamp / cold-service warm-up cap (°C).
        avg_cycles_per_quarter: Number of cycle events over the window.
        operation_vs_shutdown_fraction: Share of the window spent running, [0, 1].
        outer_diameter_mm: Component outer diameter (mm).
        wall_thickness_mm: Metal wall thickness (mm).
        insulation_thickness_mm: Insulation jacket thickness (mm).
        insulation_material: Material key into the conductivity table.
        metallurgy_family: Key into ``metal_properties`` (CARBON_STEEL etc.).
        ambient: Hourly ambient DataFrame with ``datetime`` and ``temp``.
        config: The ``temperature_series`` config block.
        rng: Seeded generator.

    Returns:
        DataFrame with columns ``datetime`` and ``process_temperature_c``,
        ``window_hours`` rows.

    Raises:
        ValueError: Unknown ``insulation_material`` or out-of-scope
            ``metallurgy_family``; ``ambient`` missing a column or shorter than
            the window; or any constraint raised by the chain functions
            (e.g. bad-bore geometry).
    """
    window_hours = int(config["window_days"]) * 24

    # Resolve material -> conductivity and metallurgy -> rho/c from config tables.
    k_table = config["insulation_conductivity_w_per_mk"]
    material_key = str(insulation_material).upper()
    if material_key not in k_table:
        raise ValueError(f"unknown insulation_material {insulation_material!r}")
    k = float(k_table[material_key])

    metals = config["metal_properties"]
    if metallurgy_family not in metals:
        raise ValueError(f"metallurgy_family {metallurgy_family!r} is out of scope")
    rho = float(metals[metallurgy_family]["density_kg_per_m3"])
    c = float(metals[metallurgy_family]["specific_heat_j_per_kg_k"])

    # Ambient: validate, slice to the window, split into temp + timestamps.
    for col in ("datetime", "temp"):
        if col not in ambient.columns:
            raise ValueError(f"ambient is missing required column {col!r}")
    if len(ambient) < window_hours:
        raise ValueError(f"ambient has {len(ambient)} rows, need >= {window_hours}")
    window = ambient.iloc[-window_hours:]
    ambient_temp = window["temp"].to_numpy(dtype=float)
    timestamps = window["datetime"].to_numpy()

    # The chain (Steps 1, 3, 4, 5, 6, 7, 8, 9).
    tau = compute_tau(
        outer_diameter_mm,
        wall_thickness_mm,
        insulation_thickness_mm,
        k,
        metal_density_kg_per_m3=rho,
        metal_specific_heat_j_per_kg_k=c,
    )
    n_cycles = int(avg_cycles_per_quarter)
    starts = place_cycles(n_cycles, window_hours)
    durations = size_cycles(
        n_cycles,
        float(operation_vs_shutdown_fraction),
        window_hours,
        int(config["min_cycle_duration_hours"]),
    )
    ref_kind = cooldown_reference(operating_temperature, min_operating_temperature)
    target = build_target_series(
        operating_temperature,
        min_operating_temperature,
        starts,
        durations,
        ref_kind,
        ambient_temp,
    )
    # Asymmetric recovery: the return to operating temperature (target == op —
    # active re-heating) uses a shorter tau than the passive excursion.
    recovery_tau_factor = float(config.get("recovery_tau_factor", 1.0))
    tau_profile = np.where(target == operating_temperature, tau * recovery_tau_factor, tau)
    temp = apply_thermal_lag(target, tau_profile)
    temp = add_running_noise(
        temp, target, operating_temperature, rng,
        float(config["running_noise_amplitude_c"]),
    )
    temp = clamp_series(
        temp,
        min_operating_temperature,
        max_operating_temperature,
        float(config["global_temperature_min_c"]),
        float(config["global_temperature_max_c"]),
    )
    return pd.DataFrame({"datetime": timestamps, "process_temperature_c": temp})
