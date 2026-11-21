
"""HTTP client for the official ThinkHazard API.

This module retrieves published ThinkHazard screening information.
It does not calculate property-level risk or financial losses.
"""

import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://thinkhazard.org/en"
DEFAULT_TIMEOUT = 15

_HAZARD_CODE_PATTERN = re.compile(r"^[A-Z]{2,3}$")


class ThinkHazardClientError(Exception):
    """Base exception for ThinkHazard client errors."""


class ThinkHazardUnavailableError(ThinkHazardClientError):
    """Raised when ThinkHazard cannot provide a usable response."""


class ThinkHazardResponseValidationError(ThinkHazardClientError):
    """Raised when the API response has an unexpected structure."""


class ThinkHazardClient:
    """Small, dependency-free client for ThinkHazard's documented API."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        parsed_url = urlsplit(base_url)

        if (
            parsed_url.scheme not in {"http", "https"}
            or not parsed_url.netloc
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise ValueError("base_url must be a valid HTTP or HTTPS URL.")

        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise ValueError("timeout must be a positive number.")

        if timeout <= 0:
            raise ValueError("timeout must be a positive number.")

        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)

    @staticmethod
    def _validate_division_code(division_code: int) -> int:
        if (
            isinstance(division_code, bool)
            or not isinstance(division_code, int)
            or division_code <= 0
        ):
            raise ValueError("division_code must be a positive integer.")

        return division_code

    @staticmethod
    def _validate_hazard_type(hazard_type: str) -> str:
        if (
            not isinstance(hazard_type, str)
            or not _HAZARD_CODE_PATTERN.fullmatch(hazard_type)
        ):
            raise ValueError(
                "hazard_type must be a valid uppercase ThinkHazard mnemonic."
            )

        return hazard_type

    def _get_json(self, path: str):
        url = f"{self.base_url}{path}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "ClimateGuardAI/1.0",
            },
            method="GET",
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                status = getattr(response, "status", 200)

                if status != 200:
                    raise ThinkHazardUnavailableError(
                        f"ThinkHazard returned HTTP status {status}."
                    )

                payload = response.read()

        except HTTPError as exc:
            raise ThinkHazardUnavailableError(
                f"ThinkHazard returned HTTP status {exc.code}."
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ThinkHazardUnavailableError(
                "Could not retrieve data from ThinkHazard."
            ) from exc

        try:
            return json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ThinkHazardResponseValidationError(
                "ThinkHazard returned invalid JSON."
            ) from exc

    def get_all_hazards(self, division_code: int) -> list[dict]:
        """Retrieve all published hazard levels for one division."""

        code = self._validate_division_code(division_code)
        payload = self._get_json(f"/report/{code}.json")

        if not isinstance(payload, list):
            raise ThinkHazardResponseValidationError(
                "Expected a list of hazard results."
            )

        for item in payload:
            if not isinstance(item, dict):
                raise ThinkHazardResponseValidationError(
                    "Each hazard result must be an object."
                )

            hazard_type = item.get("hazardtype")
            hazard_level = item.get("hazardlevel")

            if not isinstance(hazard_type, dict) or not isinstance(
                hazard_level, dict
            ):
                raise ThinkHazardResponseValidationError(
                    "Hazard results must contain hazardtype and hazardlevel."
                )

            if not isinstance(hazard_type.get("mnemonic"), str):
                raise ThinkHazardResponseValidationError(
                    "Hazard type mnemonic is missing."
                )

            if not isinstance(hazard_level.get("mnemonic"), str):
                raise ThinkHazardResponseValidationError(
                    "Hazard level mnemonic is missing."
                )

        return payload

    def get_hazard_report(
        self,
        division_code: int,
        hazard_type: str,
    ) -> dict:
        """Retrieve the detailed report for one division and hazard."""

        code = self._validate_division_code(division_code)
        hazard = self._validate_hazard_type(hazard_type)

        payload = self._get_json(
            f"/report/{code}/{hazard}.json"
        )

        if not isinstance(payload, dict):
            raise ThinkHazardResponseValidationError(
                "Expected a detailed hazard report object."
            )

        category = payload.get("hazard_category")
        if not isinstance(category, dict):
            raise ThinkHazardResponseValidationError(
                "Hazard report is missing hazard_category."
            )

        if not isinstance(category.get("hazard_level"), str):
            raise ThinkHazardResponseValidationError(
                "Hazard report is missing its hazard level."
            )

        return payload

    def get_divisions_for_hazard(
        self,
        hazard_type: str,
    ) -> list[dict]:
        """Retrieve ThinkHazard's published division list for a hazard."""

        hazard = self._validate_hazard_type(hazard_type)
        payload = self._get_json(
            f"/admindiv_hazardsets/{hazard}.json"
        )

        if not isinstance(payload, list):
            raise ThinkHazardResponseValidationError(
                "Expected a list of administrative divisions."
            )

        for item in payload:
            if not isinstance(item, dict):
                raise ThinkHazardResponseValidationError(
                    "Each administrative division must be an object."
                )

            if (
                isinstance(item.get("code"), bool)
                or not isinstance(item.get("code"), int)
                or item["code"] <= 0
            ):
                raise ThinkHazardResponseValidationError(
                    "Administrative division has an invalid code."
                )

            if not isinstance(item.get("name"), str):
                raise ThinkHazardResponseValidationError(
                    "Administrative division is missing its name."
                )

        return payload
