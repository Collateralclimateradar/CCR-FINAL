
"""Resolve UAE coordinates to ThinkHazard administrative divisions.

Boundary source: UN OCHA Global COD Admin1 ArcGIS Feature Service.
ThinkHazard division IDs are sourced from the official
GFDRR/thinkhazard support_tools/API_parse/ADM1_TH.csv dataset.
"""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ccr.services.administrative_division import (
    AdministrativeDivision,
    AdministrativeDivisionNotFoundError,
    AdministrativeDivisionResolutionError,
)


ARCGIS_QUERY_URL = (
    "https://gis.unocha.org/server/rest/services/"
    "COD/GBL_COD_Admin1/FeatureServer/0/query"
)

REQUEST_TIMEOUT_SECONDS = 15

# Official ThinkHazard ADM1 division IDs for the seven UAE emirates.
# Source:
# https://github.com/GFDRR/thinkhazard/blob/master/
# support_tools/API_parse/ADM1_TH.csv
THINKHAZARD_CODES = {
    "abu dhabi": 3173,
    "ajman": 149626,
    "dubai": 3177,
    "fujairah": 149627,
    "ras al khaimah": 3179,
    "sharjah": 3180,
    "umm al quwain": 3181,
}


class UAEEmirateResolverError(AdministrativeDivisionResolutionError):
    """Raised when the authoritative boundary service cannot be used."""


def _normalize_name(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise UAEEmirateResolverError(
            "Boundary service returned an invalid emirate name."
        )

    return " ".join(value.casefold().strip().split())


class UAEEmirateResolver:
    """Resolve a point to one UAE emirate using OCHA polygon boundaries."""

    def __init__(self, *, timeout: float = REQUEST_TIMEOUT_SECONDS) -> None:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise ValueError("timeout must be a positive number.")

        if timeout <= 0:
            raise ValueError("timeout must be a positive number.")

        self.timeout = float(timeout)

    def resolve(
        self,
        *,
        latitude: float,
        longitude: float,
    ) -> AdministrativeDivision:
        """Return the ThinkHazard division containing the supplied point."""

        if isinstance(latitude, bool) or isinstance(longitude, bool):
            raise UAEEmirateResolverError("Coordinates must be numeric.")

        try:
            lat = float(latitude)
            lon = float(longitude)
        except (TypeError, ValueError) as exc:
            raise UAEEmirateResolverError(
                "Coordinates must be numeric."
            ) from exc

        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise UAEEmirateResolverError("Coordinates are out of range.")

        geometry = json.dumps(
            {
                "x": lon,
                "y": lat,
                "spatialReference": {"wkid": 4326},
            },
            separators=(",", ":"),
        )

        params = urlencode(
            {
                "where": "adm0_pcode = 'ARE'",
                "geometry": geometry,
                "geometryType": "esriGeometryPoint",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "adm1_name,adm1_pcode,adm0_pcode",
                "returnGeometry": "false",
                "returnZ": "false",
                "f": "json",
            }
        )

        request = Request(
            f"{ARCGIS_QUERY_URL}?{params}",
            headers={
                "Accept": "application/json",
                "User-Agent": "ClimateGuardAI/1.0",
            },
            method="GET",
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise UAEEmirateResolverError(
                f"Boundary service returned HTTP {exc.code}."
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise UAEEmirateResolverError(
                "Could not reach the UAE boundary service."
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UAEEmirateResolverError(
                "Boundary service returned invalid JSON."
            ) from exc

        if not isinstance(payload, dict):
            raise UAEEmirateResolverError(
                "Boundary service returned an unexpected response."
            )

        if payload.get("error"):
            raise UAEEmirateResolverError(
                "Boundary service reported a query error."
            )

        features = payload.get("features")

        if not isinstance(features, list):
            raise UAEEmirateResolverError(
                "Boundary response is missing its features list."
            )

        if not features:
            raise AdministrativeDivisionNotFoundError(
                "Coordinates do not match a UAE emirate boundary."
            )

        if len(features) != 1:
            raise UAEEmirateResolverError(
                "Coordinates match multiple emirate boundaries; "
                "the location is ambiguous."
            )

        feature = features[0]
        attributes = (
            feature.get("attributes")
            if isinstance(feature, dict)
            else None
        )

        if not isinstance(attributes, dict):
            raise UAEEmirateResolverError(
                "Boundary feature is missing its attributes."
            )

        if attributes.get("adm0_pcode") != "ARE":
            raise UAEEmirateResolverError(
                "Boundary feature is not identified as the UAE."
            )

        emirate_name = _normalize_name(attributes.get("adm1_name"))
        thinkhazard_code = THINKHAZARD_CODES.get(emirate_name)

        if thinkhazard_code is None:
            raise UAEEmirateResolverError(
                "The returned emirate has no verified ThinkHazard mapping."
            )

        return AdministrativeDivision(
            code=thinkhazard_code,
            name=emirate_name.title(),
            country="United Arab Emirates",
            admin1=emirate_name.title(),
            admin2=None,
        )
