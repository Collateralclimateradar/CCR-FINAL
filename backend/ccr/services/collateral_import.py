
"""CSV parsing and validation for collateral imports.

This module validates uploaded data only. It never writes to the database.
"""

import csv
import io
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from ccr.schemas.collateral import CollateralCreate
from ccr.schemas.collateral_import import (
    CollateralImportPreview,
    CollateralImportRowPreview,
    ImportIssue,
)


MAX_CSV_BYTES = 10 * 1024 * 1024
MAX_CSV_ROWS = 10_000

REQUIRED_HEADERS = {
    "external_ref",
    "property_type",
    "is_synthetic",
}

ALLOWED_HEADERS = {
    "external_ref",
    "property_type",
    "description",
    "country_code",
    "region",
    "city",
    "latitude",
    "longitude",
    "is_synthetic",
}


class CSVImportError(ValueError):
    """Raised when the uploaded CSV file cannot be processed."""


@dataclass
class CSVValidationResult:
    """Preview plus validated payloads for a later import operation."""

    preview: CollateralImportPreview
    valid_records: list[dict[str, Any]]


def _add_issue(
    issues: list[ImportIssue],
    row_number: int,
    code: str,
    message: str,
    field: str | None = None,
) -> None:
    issues.append(
        ImportIssue(
            row_number=row_number,
            field=field,
            code=code,
            message=message,
            severity="error",
        )
    )


def _normalize_row(
    row: dict[str, Any],
) -> dict[str, Any]:
    """Convert empty CSV cells to None and trim string values."""

    normalized = {}

    for key, value in row.items():
        if key is None:
            continue

        if isinstance(value, str):
            value = value.strip()
            normalized[key] = value if value else None
        else:
            normalized[key] = value

    return normalized


def validate_collateral_csv(content: bytes) -> CSVValidationResult:
    """Parse and validate CSV bytes without persisting any records."""

    if not isinstance(content, bytes):
        raise TypeError("CSV content must be bytes.")

    if not content:
        raise CSVImportError("The uploaded CSV file is empty.")

    if len(content) > MAX_CSV_BYTES:
        raise CSVImportError("The CSV file exceeds the 10 MB limit.")

    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CSVImportError(
            "The CSV file must use UTF-8 encoding."
        ) from exc

    try:
        reader = csv.DictReader(
            io.StringIO(decoded, newline=""),
            strict=True,
        )

        headers = reader.fieldnames

        if not headers:
            raise CSVImportError("The CSV file has no header row.")

        normalized_headers = [
            header.strip() if header else ""
            for header in headers
        ]

        if any(not header for header in normalized_headers):
            raise CSVImportError(
                "The CSV header contains an empty column name."
            )

        if len(normalized_headers) != len(set(normalized_headers)):
            raise CSVImportError(
                "The CSV file contains duplicate column names."
            )

        missing_headers = REQUIRED_HEADERS - set(normalized_headers)

        if missing_headers:
            missing = ", ".join(sorted(missing_headers))
            raise CSVImportError(
                f"Missing required CSV columns: {missing}."
            )

        unsupported_headers = (
            set(normalized_headers) - ALLOWED_HEADERS
        )

        if unsupported_headers:
            unsupported = ", ".join(sorted(unsupported_headers))
            raise CSVImportError(
                f"Unsupported CSV columns: {unsupported}."
            )

        reader.fieldnames = normalized_headers

        preview_rows = []
        all_issues = []
        valid_records = []
        seen_refs = set()
        total_rows = 0

        for row_number, raw_row in enumerate(reader, start=2):
            if row_number - 1 > MAX_CSV_ROWS:
                raise CSVImportError(
                    "The CSV file exceeds the 10,000 row limit."
                )

            if raw_row is None:
                continue

            if None in raw_row:
                issues = []
                _add_issue(
                    issues,
                    row_number,
                    "EXTRA_VALUES",
                    "This row contains more values than the header.",
                )
                total_rows += 1
                preview_rows.append(
                    CollateralImportRowPreview(
                        row_number=row_number,
                        external_ref=None,
                        is_valid=False,
                        issues=issues,
                    )
                )
                all_issues.extend(issues)
                continue

            normalized = _normalize_row(raw_row)

            if not any(value is not None for value in normalized.values()):
                continue

            total_rows += 1
            row_issues = []

            external_ref = normalized.get("external_ref")

            if external_ref:
                if external_ref in seen_refs:
                    _add_issue(
                        row_issues,
                        row_number,
                        "DUPLICATE_EXTERNAL_REF",
                        "This external reference appears more than once in the file.",
                        "external_ref",
                    )
                else:
                    seen_refs.add(external_ref)

            validated_data = None

            try:
                validated = CollateralCreate.model_validate(normalized)
                validated_data = validated.model_dump()
            except ValidationError as exc:
                for error in exc.errors():
                    field_path = error.get("loc", ())
                    field = (
                        str(field_path[0])
                        if field_path
                        else None
                    )
                    _add_issue(
                        row_issues,
                        row_number,
                        "INVALID_FIELD",
                        "The supplied value is invalid or missing.",
                        field,
                    )

            is_valid = not row_issues and validated_data is not None

            if is_valid:
                valid_records.append(validated_data)

            preview_rows.append(
                CollateralImportRowPreview(
                    row_number=row_number,
                    external_ref=external_ref,
                    is_valid=is_valid,
                    issues=row_issues,
                )
            )
            all_issues.extend(row_issues)

        valid_count = sum(
            1 for row in preview_rows if row.is_valid
        )

        invalid_count = total_rows - valid_count

        preview = CollateralImportPreview(
            total_rows=total_rows,
            valid_rows=valid_count,
            invalid_rows=invalid_count,
            rows=preview_rows,
            issues=all_issues,
        )

        return CSVValidationResult(
            preview=preview,
            valid_records=valid_records,
        )

    except csv.Error as exc:
        raise CSVImportError(
            "The CSV file has invalid formatting."
        ) from exc
