
"""Transactional persistence for validated collateral CSV imports."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ccr.models import Collateral
from ccr.schemas.collateral_import import (
    CollateralImportReport,
    ImportIssue,
)
from ccr.services.collateral_import import CSVValidationResult


class CollateralImportConflict(Exception):
    """Raised when imported records conflict with existing data."""


def execute_collateral_import(
    db: Session,
    organization_id: uuid.UUID,
    validation_result: CSVValidationResult,
) -> CollateralImportReport:
    """
    Persist valid CSV records for one organization in a single transaction.

    Invalid CSV rows and existing external references are skipped.
    Any database integrity conflict rolls back the entire import.
    """

    preview = validation_result.preview
    records = validation_result.valid_records

    external_refs = [
        record["external_ref"]
        for record in records
    ]

    existing_refs: set[str] = set()

    if external_refs:
        existing_refs = set(
            db.scalars(
                select(Collateral.external_ref).where(
                    Collateral.organization_id == organization_id,
                    Collateral.external_ref.in_(external_refs),
                )
            ).all()
        )

    importable_records = []
    additional_issues = []
    existing_duplicate_count = 0

    # Valid records correspond to valid preview rows in their original order.
    valid_rows = [
        row for row in preview.rows if row.is_valid
    ]

    if len(valid_rows) != len(records):
        raise ValueError(
            "Validated records do not match the preview rows."
        )

    for row, record in zip(valid_rows, records):
        external_ref = record["external_ref"]

        if external_ref in existing_refs:
            existing_duplicate_count += 1
            additional_issues.append(
                ImportIssue(
                    row_number=row.row_number,
                    field="external_ref",
                    code="EXTERNAL_REF_ALREADY_EXISTS",
                    message=(
                        "This external reference already exists "
                        "in this organization."
                    ),
                    severity="error",
                )
            )
            continue

        importable_records.append(
            Collateral(
                organization_id=organization_id,
                **record,
            )
        )

    try:
        db.add_all(importable_records)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise CollateralImportConflict(
            "The import conflicts with existing database records. "
            "No records were imported."
        ) from exc

    imported_count = len(importable_records)
    skipped_count = preview.invalid_rows + existing_duplicate_count

    return CollateralImportReport(
        total_rows=preview.total_rows,
        imported_rows=imported_count,
        skipped_rows=skipped_count,
        failed_rows=0,
        issues=preview.issues + additional_issues,
    )
