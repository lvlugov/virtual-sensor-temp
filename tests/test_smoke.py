"""Minimal import check until real tests are added."""

import virtual_sensor


def test_package_importable() -> None:
    assert virtual_sensor.__version__
