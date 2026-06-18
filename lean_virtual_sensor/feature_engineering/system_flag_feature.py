"""Derive the NACE open/closed system flag from asset condition strings.

A closed system — water trapped against the steel by intact insulation and
cladding — requires BOTH insulation AND cladding to be in GOOD condition.
Any compromise to either lets atmospheric moisture in (and oxygen-bearing
water out), so the system is effectively open from the NACE corrosion-
mechanism standpoint. That binary in turn chooses between :func:`compute_f_open`
and :func:`compute_f_closed` in the asset-temperature pipeline.
"""

VALID_CONDITIONS = frozenset({"GOOD", "AVERAGE", "POOR"})


def is_open_system(insulation_condition: str, cladding_integrity: str) -> bool:
    """Return True when the asset behaves as an open NACE system.

    Args:
        insulation_condition: One of ``"GOOD"``, ``"AVERAGE"``, ``"POOR"``
            (case-insensitive).
        cladding_integrity: One of ``"GOOD"``, ``"AVERAGE"``, ``"POOR"``
            (case-insensitive).

    Returns:
        ``False`` (closed) only when both inputs are ``"GOOD"``; ``True``
        (open) otherwise.

    Raises:
        ValueError: If either input is not one of the three valid condition
            strings.
    """
    ins = insulation_condition.strip().upper()
    clad = cladding_integrity.strip().upper()
    if ins not in VALID_CONDITIONS:
        raise ValueError(
            f"insulation_condition must be one of {sorted(VALID_CONDITIONS)}, "
            f"got {insulation_condition!r}"
        )
    if clad not in VALID_CONDITIONS:
        raise ValueError(
            f"cladding_integrity must be one of {sorted(VALID_CONDITIONS)}, "
            f"got {cladding_integrity!r}"
        )
    return not (ins == "GOOD" and clad == "GOOD")
