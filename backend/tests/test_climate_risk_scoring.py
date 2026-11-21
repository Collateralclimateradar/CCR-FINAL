
"""Tests for CCR climate risk scoring and assessment synchronization."""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from ccr.services.climate_risk_scoring import (
    apply_risk_score,
    classify_risk,
)


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0, "low"),
        (1, "low"),
        (24.99, "low"),
        (25, "moderate"),
        (49.99, "moderate"),
        (50, "high"),
        (74.99, "high"),
        (75, "very_high"),
        (100, "very_high"),
    ],
)
def test_classify_risk(score, expected):
    assert classify_risk(score) == expected


@pytest.mark.parametrize(
    "score",
    [-1, -0.01, 100.01, 101],
)
def test_rejects_out_of_range_scores(score):
    with pytest.raises(ValueError, match="between 0 and 100"):
        classify_risk(score)


@pytest.mark.parametrize(
    "score",
    ["invalid", "", None, "abc"],
)
def test_rejects_invalid_numeric_scores(score):
    with pytest.raises(ValueError, match="valid number"):
        classify_risk(score)


@pytest.mark.parametrize(
    "score",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_rejects_non_finite_scores(score):
    with pytest.raises(ValueError, match="finite"):
        classify_risk(score)


@pytest.mark.parametrize(
    ("score", "expected_level"),
    [
        (Decimal("10"), "low"),
        (Decimal("30"), "moderate"),
        (Decimal("60"), "high"),
        (Decimal("90"), "very_high"),
    ],
)
def test_apply_risk_score_synchronizes_score_and_level(
    score,
    expected_level,
):
    assessment = SimpleNamespace(
        risk_score=Decimal("0"),
        risk_level="low",
    )

    result = apply_risk_score(assessment, score)

    assert result is assessment
    assert assessment.risk_score == score
    assert assessment.risk_level == expected_level


def test_apply_risk_score_corrects_existing_mismatch():
    assessment = SimpleNamespace(
        risk_score=Decimal("90"),
        risk_level="low",
    )

    apply_risk_score(assessment, Decimal("90"))

    assert assessment.risk_score == Decimal("90")
    assert assessment.risk_level == "very_high"


def test_apply_risk_score_rejects_invalid_score_without_mutating():
    assessment = SimpleNamespace(
        risk_score=Decimal("20"),
        risk_level="low",
    )

    with pytest.raises(ValueError):
        apply_risk_score(assessment, 150)

    assert assessment.risk_score == Decimal("20")
    assert assessment.risk_level == "low"
