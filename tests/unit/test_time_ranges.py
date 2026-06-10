from __future__ import annotations

import pytest

from src.models.time_ranges import validate_timestamp_range


def test_required_timestamp_range_accepts_increasing_values() -> None:
    validate_timestamp_range(1.0, 2.0, required=True)


def test_required_timestamp_range_rejects_missing_value() -> None:
    with pytest.raises(ValueError, match="required"):
        validate_timestamp_range(1.0, None, required=True)


def test_optional_timestamp_range_accepts_missing_values() -> None:
    validate_timestamp_range(None, None, required=False)
    validate_timestamp_range(1.0, None, required=False)
    validate_timestamp_range(None, 2.0, required=False)


def test_timestamp_range_rejects_end_before_start() -> None:
    with pytest.raises(ValueError, match="greater than start"):
        validate_timestamp_range(2.0, 1.0, required=True)


def test_timestamp_range_rejects_equal_start_and_end() -> None:
    with pytest.raises(ValueError, match="greater than start"):
        validate_timestamp_range(2.0, 2.0, required=False)
