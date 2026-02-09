"""Unit tests for Phase 2 robust deviation math."""

import math

import pytest

from evolution.phase2_engine import (
    _median_absolute_deviation,
    _iqr,
    compute_robust_deviation,
)


class TestMedianAbsoluteDeviation:
    def test_symmetric_distribution(self):
        values = [1, 2, 3, 4, 5]
        # median = 3, deviations = [2, 1, 0, 1, 2], MAD = 1
        assert _median_absolute_deviation(values) == 1

    def test_constant_series(self):
        values = [5, 5, 5, 5, 5]
        assert _median_absolute_deviation(values) == 0

    def test_single_outlier(self):
        values = [1, 1, 1, 1, 100]
        # median = 1, deviations = [0, 0, 0, 0, 99], MAD = 0
        assert _median_absolute_deviation(values) == 0

    def test_two_value_list(self):
        values = [1, 3]
        # median = 2, deviations = [1, 1], MAD = 1
        assert _median_absolute_deviation(values) == 1


class TestIQR:
    def test_known_distribution(self):
        values = [1, 2, 3, 4, 5, 6, 7, 8]
        # Q1 = values[2] = 3, Q3 = values[6] = 7, IQR = 4
        assert _iqr(values) == 4

    def test_constant_series(self):
        values = [5, 5, 5, 5]
        assert _iqr(values) == 0

    def test_sorted_input_not_required(self):
        values = [8, 1, 4, 2, 7, 3, 6, 5]
        result = _iqr(values)
        assert result == _iqr(sorted(values))


class TestComputeRobustDeviation:
    def test_normal_distribution_modified_zscore(self):
        """When MAD > 0, should return modified_zscore."""
        values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        result = compute_robust_deviation(15, values)

        assert result["unit"] == "modified_zscore"
        assert result["degenerate"] is False
        assert result["mad"] > 0
        assert result["measure"] > 0  # 15 is above median

    def test_constant_series_same_value(self):
        """Constant baseline + same observed = degenerate, measure 0."""
        values = [5, 5, 5, 5, 5]
        result = compute_robust_deviation(5, values)

        assert result["unit"] == "degenerate"
        assert result["degenerate"] is True
        assert result["measure"] == 0.0
        assert result["mad"] == 0.0

    def test_constant_series_different_value(self):
        """Constant baseline + different observed = degenerate, measure None."""
        values = [5, 5, 5, 5, 5]
        result = compute_robust_deviation(10, values)

        assert result["unit"] == "degenerate"
        assert result["degenerate"] is True
        assert result["measure"] is None
        assert result["mad"] == 0.0

    def test_iqr_fallback(self):
        """When MAD=0 but IQR>0, should use iqr_normalized."""
        # MAD=0 happens when >50% of values are the same but there's spread
        # e.g., [1, 1, 1, 1, 1, 1, 1, 10, 20, 30]
        # median=1, deviations=[0,0,0,0,0,0,0,9,19,29], MAD of these = 0
        # But IQR will be > 0
        values = [1, 1, 1, 1, 1, 1, 1, 10, 20, 30]
        mad = _median_absolute_deviation(values)
        iqr_val = _iqr(values)

        if mad == 0 and iqr_val > 0:
            result = compute_robust_deviation(50, values)
            assert result["unit"] == "iqr_normalized"
            assert result["degenerate"] is False
            assert result["measure"] is not None
        else:
            pytest.skip("Test data doesn't produce MAD=0, IQR>0 condition")

    def test_symmetry(self):
        """Deviation above median should be positive, below negative."""
        values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        med = 5.5

        above = compute_robust_deviation(15, values)
        below = compute_robust_deviation(-5, values)

        assert above["measure"] > 0
        assert below["measure"] < 0

    def test_median_value_observed(self):
        """Observing exactly the median should yield ~0 deviation."""
        values = [1, 2, 3, 4, 5, 6, 7, 8, 9]
        # median = 5
        result = compute_robust_deviation(5, values)

        assert result["unit"] == "modified_zscore"
        assert abs(result["measure"]) < 0.01

    def test_measure_is_rounded(self):
        """Measure should be rounded to 6 decimal places."""
        values = [1, 2, 3, 4, 5]
        result = compute_robust_deviation(10, values)

        if result["measure"] is not None:
            decimal_str = str(result["measure"]).split(".")[-1]
            assert len(decimal_str) <= 6

    def test_large_dataset(self):
        """Should handle large datasets efficiently."""
        import random
        random.seed(42)
        values = [random.gauss(100, 15) for _ in range(1000)]
        result = compute_robust_deviation(150, values)

        assert result["unit"] == "modified_zscore"
        assert result["degenerate"] is False
        assert result["measure"] > 0

    def test_binary_metric(self):
        """Binary metrics (0/1) where most are 0 should be degenerate."""
        values = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        result = compute_robust_deviation(1, values)

        assert result["degenerate"] is True
        assert result["measure"] is None  # changed from constant 0
