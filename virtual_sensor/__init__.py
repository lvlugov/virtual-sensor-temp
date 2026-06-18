"""Corrosion Radar *virtual sensor* repository — umbrella package.

Python code for the two product lines lives in separate top-level packages:

- ``advanced_virtual_sensor`` — deterministic pipeline pieces (e.g. ``asset_similarity``,
  ``water_factor``, ``risk_calc``).
- ``lean_virtual_sensor`` — lean virtual sensor data paths and generators (see that tree).

This module exists so ``import virtual_sensor`` resolves to a single project root package
(version metadata only); it does not re-export the advanced or lean subpackages.
"""

__version__ = "0.1.0"
