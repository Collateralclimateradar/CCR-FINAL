
"""Response schemas for collateral CSV import operations."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ImportIssue(BaseModel):
    """A validation issue associated with one CSV row."""

    model_config = ConfigDict(extra="forbid")

    row_number: int = Field(ge=1)
    field: str | None = None
    code: str = Field(min_length=1, max_length=50)
    message: str = Field(min_length=1, max_length=500)
    severity: Literal["error", "warning"] = "error"


class CollateralImportRowPreview(BaseModel):
    """Safe preview of one parsed CSV row."""

    model_config = ConfigDict(extra="forbid")

    row_number: int = Field(ge=1)
    external_ref: str | None = None
    is_valid: bool
    issues: list[ImportIssue] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_row_status(self):
        has_errors = any(
            issue.severity == "error"
            for issue in self.issues
        )

        if self.is_valid == has_errors:
            raise ValueError(
                "is_valid must be false when errors exist "
                "and true when no errors exist."
            )

        return self


class CollateralImportPreview(BaseModel):
    """Summary returned after validating an uploaded CSV."""

    model_config = ConfigDict(extra="forbid")

    total_rows: int = Field(ge=0)
    valid_rows: int = Field(ge=0)
    invalid_rows: int = Field(ge=0)
    rows: list[CollateralImportRowPreview]
    issues: list[ImportIssue] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_counts(self):
        if self.valid_rows + self.invalid_rows != self.total_rows:
            raise ValueError(
                "valid_rows + invalid_rows must equal total_rows."
            )

        if len(self.rows) > self.total_rows:
            raise ValueError(
                "Preview rows cannot exceed total_rows."
            )

        return self


class CollateralImportReport(BaseModel):
    """Final result of a collateral import operation."""

    model_config = ConfigDict(extra="forbid")

    total_rows: int = Field(ge=0)
    imported_rows: int = Field(ge=0)
    skipped_rows: int = Field(ge=0)
    failed_rows: int = Field(ge=0)
    issues: list[ImportIssue] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_counts(self):
        if (
            self.imported_rows
            + self.skipped_rows
            + self.failed_rows
            != self.total_rows
        ):
            raise ValueError(
                "Imported, skipped, and failed rows "
                "must equal total_rows."
            )

        return self
