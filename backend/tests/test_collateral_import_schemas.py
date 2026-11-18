
import pytest
from pydantic import ValidationError

from ccr.schemas.collateral_import import (
    CollateralImportPreview,
    CollateralImportReport,
    CollateralImportRowPreview,
    ImportIssue,
)


def test_valid_import_row():
    row = CollateralImportRowPreview(
        row_number=2,
        external_ref="COL-001",
        is_valid=True,
        issues=[],
    )

    assert row.is_valid is True
    assert row.external_ref == "COL-001"


def test_invalid_import_row_requires_error_issue():
    with pytest.raises(ValidationError):
        CollateralImportRowPreview(
            row_number=2,
            external_ref="COL-001",
            is_valid=False,
            issues=[],
        )


def test_valid_row_can_contain_warning():
    row = CollateralImportRowPreview(
        row_number=2,
        external_ref="COL-001",
        is_valid=True,
        issues=[
            ImportIssue(
                row_number=2,
                field="city",
                code="MISSING_CITY",
                message="City was not provided.",
                severity="warning",
            )
        ],
    )

    assert row.is_valid is True
    assert len(row.issues) == 1


def test_invalid_row_with_error_issue():
    row = CollateralImportRowPreview(
        row_number=3,
        external_ref=None,
        is_valid=False,
        issues=[
            ImportIssue(
                row_number=3,
                field="external_ref",
                code="MISSING_REQUIRED_FIELD",
                message="External reference is required.",
            )
        ],
    )

    assert row.is_valid is False


def test_preview_counts_must_match():
    with pytest.raises(ValidationError):
        CollateralImportPreview(
            total_rows=10,
            valid_rows=8,
            invalid_rows=1,
            rows=[],
        )


def test_preview_rows_cannot_exceed_total():
    with pytest.raises(ValidationError):
        CollateralImportPreview(
            total_rows=1,
            valid_rows=1,
            invalid_rows=0,
            rows=[
                CollateralImportRowPreview(
                    row_number=2,
                    external_ref="COL-002",
                    is_valid=True,
                ),
                CollateralImportRowPreview(
                    row_number=3,
                    external_ref="COL-003",
                    is_valid=True,
                ),
            ],
        )


def test_valid_import_report():
    report = CollateralImportReport(
        total_rows=10,
        imported_rows=8,
        skipped_rows=1,
        failed_rows=1,
    )

    assert report.imported_rows == 8
    assert report.total_rows == 10


def test_import_report_rejects_inconsistent_counts():
    with pytest.raises(ValidationError):
        CollateralImportReport(
            total_rows=10,
            imported_rows=8,
            skipped_rows=0,
            failed_rows=1,
        )


def test_issue_rejects_invalid_severity():
    with pytest.raises(ValidationError):
        ImportIssue(
            row_number=2,
            code="INVALID",
            message="Invalid issue.",
            severity="critical",
        )
