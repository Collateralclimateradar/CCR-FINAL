
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
from ccr.services.audit import record_audit_event
from ccr.services.collateral_import import CSVValidationResult


class CollateralImportConflict(Exception):
    """Raised when imported records conflict with existing data."""


def execute_collateral_import(
    db: Session,
    organization_id: uuid.UUID,
    validation_result: CSVValidationResult,
    actor_user_id: uuid.UUID | None = None,
) -> CollateralImportReport:
    """
    Persist valid CSV records and audit the operation
    in the same database transaction.
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

    imported_count = len(importable_records)
    skipped_count = (
        preview.invalid_rows + existing_duplicate_count
    )

    report = CollateralImportReport(
        total_rows=preview.total_rows,
        imported_rows=imported_count,
        skipped_rows=skipped_count,
        failed_rows=0,
        issues=preview.issues + additional_issues,
    )

    try:
        db.add_all(importable_records)
        db.flush()

        record_audit_event(
            db,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="collateral.imported",
            entity_type="collateral_import",
            entity_id=uuid.uuid4(),
            after_data={
                "total_rows": report.total_rows,
                "imported_rows": report.imported_rows,
                "skipped_rows": report.skipped_rows,
                "failed_rows": report.failed_rows,
            },
        )

        db.commit()

    except IntegrityError as exc:
        db.rollback()

        raise CollateralImportConflict(
            "The import conflicts with existing database records. "
            "No records were imported."
        ) from exc

    except Exception:
        db.rollback()
        raise

    return report
