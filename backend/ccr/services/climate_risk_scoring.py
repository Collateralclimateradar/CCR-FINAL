
"""Climate risk scoring and assessment synchronization for CCR."""

from decimal import Decimal, InvalidOperation
from typing import Final

LOW: Final[str] = "low"
MODERATE: Final[str] = "moderate"
HIGH: Final[str] = "high"
VERY_HIGH: Final[str] = "very_high"

MIN_SCORE: Final[Decimal] = Decimal("0")
MAX_SCORE: Final[Decimal] = Decimal("100")

MODEL_VERSION: Final[str] = "1.0"


def normalize_score(score: Decimal | int | float | str) -> Decimal:
    """Convert a score into a validated Decimal between 0 and 100."""

    try:
        value = Decimal(str(score))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Risk score must be a valid number.") from None

    if not value.is_finite():
        raise ValueError("Risk score must be finite.")

    if not MIN_SCORE <= value <= MAX_SCORE:
        raise ValueError("Risk score must be between 0 and 100.")

    return value


def classify_risk(score: Decimal | int | float | str) -> str:
    """Classify a normalized climate risk score.

    Provisional classification bands:
        0 <= score < 25: low
        25 <= score < 50: moderate
        50 <= score < 75: high
        75 <= score <= 100: very_high

    These bands are not calibrated hazard probabilities
    or financial loss estimates.
    """

    value = normalize_score(score)

    if value < Decimal("25"):
        return LOW

    if value < Decimal("50"):
        return MODERATE

    if value < Decimal("75"):
        return HIGH

    return VERY_HIGH


def apply_risk_score(assessment, score):
    """Synchronize the assessment's risk score and risk level.

    The classification is always calculated internally.
    The caller cannot provide a separate risk level.
    """

    value = normalize_score(score)
    level = classify_risk(value)

    assessment.risk_score = value
    assessment.risk_level = level

    return assessment
