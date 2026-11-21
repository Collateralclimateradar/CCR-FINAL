
"""Climate risk score classification for CCR."""

from decimal import Decimal, InvalidOperation
from typing import Final

LOW: Final[str] = "low"
MODERATE: Final[str] = "moderate"
HIGH: Final[str] = "high"
VERY_HIGH: Final[str] = "very_high"

MIN_SCORE: Final[Decimal] = Decimal("0")
MAX_SCORE: Final[Decimal] = Decimal("100")

MODEL_VERSION: Final[str] = "1.0"


def classify_risk(score: Decimal | int | float | str) -> str:
    """Classify a normalized climate risk score from 0 to 100.

    Provisional classification bands:
        0 <= score < 25: low
        25 <= score < 50: moderate
        50 <= score < 75: high
        75 <= score <= 100: very_high

    These thresholds are classification bands, not calibrated
    hazard probabilities or financial loss estimates.
    """
    try:
        value = Decimal(str(score))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Risk score must be a valid number.") from None

    if not value.is_finite():
        raise ValueError("Risk score must be finite.")

    if not MIN_SCORE <= value <= MAX_SCORE:
        raise ValueError("Risk score must be between 0 and 100.")

    if value < Decimal("25"):
        return LOW

    if value < Decimal("50"):
        return MODERATE

    if value < Decimal("75"):
        return HIGH

    return VERY_HIGH
