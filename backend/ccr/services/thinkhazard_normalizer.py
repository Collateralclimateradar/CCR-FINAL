
"""Normalize ThinkHazard classifications into CCR climate results."""

from datetime import datetime, timezone

from ccr.services.climate_data_provider import (
    ClimateHazard,
    ClimateHazardResult,
    ClimateDataValidationError,
    HazardLevel,
    validate_coordinates,
    validate_provider_result,
)


SOURCE_NAME = "thinkhazard"

HAZARD_MAPPING = {
    "FL": ClimateHazard.FLOOD,
    "UF": ClimateHazard.FLOOD,
    "CF": ClimateHazard.COASTAL,
    "EH": ClimateHazard.EXTREME_HEAT,
}

LEVEL_MAPPING = {
    "VLO": HazardLevel.LOW,
    "LOW": HazardLevel.LOW,
    "MED": HazardLevel.MODERATE,
    "HIG": HazardLevel.HIGH,
}

LEVEL_RANK = {
    HazardLevel.LOW: 1,
    HazardLevel.MODERATE: 2,
    HazardLevel.HIGH: 3,
    HazardLevel.VERY_HIGH: 4,
    HazardLevel.UNKNOWN: 0,
}


class ThinkHazardNormalizationError(Exception):
    """Raised when ThinkHazard data cannot be normalized safely."""


def normalize_thinkhazard_results(
    payload: list[dict],
    *,
    division_code: int,
    latitude: float,
    longitude: float,
    retrieved_at: datetime | None = None,
    hazards: tuple[ClimateHazard, ...] | None = None,
) -> list[ClimateHazardResult]:
    """Convert ThinkHazard's all-hazards response to CCR results.

    River flood and urban flood are combined into one flood result.
    If both are present, the higher classification is retained.
    Unsupported hazard types are ignored.

    ThinkHazard's Very Low classification is represented as LOW because
    CCR's normalized contract does not have a VERY_LOW level. The original
    classification is preserved in raw_category.
    """

    if (
        isinstance(division_code, bool)
        or not isinstance(division_code, int)
        or division_code <= 0
    ):
        raise ThinkHazardNormalizationError(
            "division_code must be a positive integer."
        )

    try:
        lat, lon = validate_coordinates(latitude, longitude)
    except ClimateDataValidationError as exc:
        raise ThinkHazardNormalizationError(str(exc)) from exc

    if not isinstance(payload, list):
        raise ThinkHazardNormalizationError(
            "ThinkHazard payload must be a list."
        )

    if retrieved_at is None:
        retrieved_at = datetime.now(timezone.utc)

    if not isinstance(retrieved_at, datetime):
        raise ThinkHazardNormalizationError(
            "retrieved_at must be a datetime."
        )

    if hazards is None:
        requested_hazards = set(ClimateHazard)
    else:
        if not isinstance(hazards, tuple) or any(
            not isinstance(item, ClimateHazard) for item in hazards
        ):
            raise ThinkHazardNormalizationError(
                "hazards must be a tuple of ClimateHazard values."
            )
        requested_hazards = set(hazards)

    aggregated = {}

    for item in payload:
        if not isinstance(item, dict):
            raise ThinkHazardNormalizationError(
                "Each hazard entry must be an object."
            )

        hazard_type = item.get("hazardtype")
        hazard_level = item.get("hazardlevel")

        if not isinstance(hazard_type, dict) or not isinstance(
            hazard_level, dict
        ):
            raise ThinkHazardNormalizationError(
                "Each entry must contain hazardtype and hazardlevel objects."
            )

        mnemonic = hazard_type.get("mnemonic")
        level_mnemonic = hazard_level.get("mnemonic")

        if not isinstance(mnemonic, str):
            raise ThinkHazardNormalizationError(
                "Hazard mnemonic is missing."
            )

        if not isinstance(level_mnemonic, str):
            raise ThinkHazardNormalizationError(
                "Hazard level mnemonic is missing."
            )

        normalized_hazard = HAZARD_MAPPING.get(mnemonic)

        if normalized_hazard is None:
            continue

        if normalized_hazard not in requested_hazards:
            continue

        normalized_level = LEVEL_MAPPING.get(level_mnemonic)

        if normalized_level is None:
            raise ThinkHazardNormalizationError(
                f"Unsupported ThinkHazard level: {level_mnemonic}"
            )

        raw_category = hazard_level.get("title")
        if not isinstance(raw_category, str) or not raw_category.strip():
            raw_category = level_mnemonic

        current = aggregated.get(normalized_hazard)

        if current is None or LEVEL_RANK[normalized_level] > LEVEL_RANK[
            current["level"]
        ]:
            aggregated[normalized_hazard] = {
                "level": normalized_level,
                "raw_category": raw_category,
                "mnemonics": [mnemonic],
            }
        elif mnemonic not in current["mnemonics"]:
            current["mnemonics"].append(mnemonic)

    results = []

    for hazard, data in aggregated.items():
        result = ClimateHazardResult(
            source=SOURCE_NAME,
            hazard=hazard,
            level=data["level"],
            retrieved_at=retrieved_at,
            latitude=lat,
            longitude=lon,
            raw_category=data["raw_category"],
            reference_url=(
                f"https://thinkhazard.org/en/report/"
                f"{division_code}/{','.join(data['mnemonics'])}"
            ),
        )

        results.append(validate_provider_result(result))

    return results
