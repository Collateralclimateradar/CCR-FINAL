
import pytest

from ccr.services.collateral_import import (
    CSVImportError,
    MAX_CSV_BYTES,
    validate_collateral_csv,
)


def csv_bytes(content: str) -> bytes:
    return content.encode("utf-8")


def test_valid_csv_returns_valid_records():
    content = csv_bytes(
        "external_ref,property_type,is_synthetic,city\n"
        "COL-001,villa,true,Dubai\n"
        "COL-002,apartment,false,Abu Dhabi\n"
    )

    result = validate_collateral_csv(content)

    assert result.preview.total_rows == 2
    assert result.preview.valid_rows == 2
    assert result.preview.invalid_rows == 0
    assert len(result.valid_records) == 2
    assert result.valid_records[0]["external_ref"] == "COL-001"


def test_missing_required_header_is_rejected():
    content = csv_bytes(
        "external_ref,property_type\n"
        "COL-001,villa\n"
    )

    with pytest.raises(CSVImportError):
        validate_collateral_csv(content)


def test_unsupported_header_is_rejected():
    content = csv_bytes(
        "external_ref,property_type,is_synthetic,password\n"
        "COL-001,villa,true,test\n"
    )

    with pytest.raises(CSVImportError):
        validate_collateral_csv(content)


def test_duplicate_headers_are_rejected():
    content = csv_bytes(
        "external_ref,external_ref,property_type,is_synthetic\n"
        "COL-001,COL-002,villa,true\n"
    )

    with pytest.raises(CSVImportError):
        validate_collateral_csv(content)


def test_invalid_utf8_is_rejected():
    with pytest.raises(CSVImportError):
        validate_collateral_csv(b"\xff\xfe\xfa")


def test_empty_file_is_rejected():
    with pytest.raises(CSVImportError):
        validate_collateral_csv(b"")


def test_file_size_limit_is_enforced():
    content = b"x" * (MAX_CSV_BYTES + 1)

    with pytest.raises(CSVImportError):
        validate_collateral_csv(content)


def test_duplicate_external_refs_are_detected():
    content = csv_bytes(
        "external_ref,property_type,is_synthetic\n"
        "COL-001,villa,true\n"
        "COL-001,apartment,true\n"
    )

    result = validate_collateral_csv(content)

    assert result.preview.total_rows == 2
    assert result.preview.valid_rows == 0
    assert result.preview.invalid_rows == 2
    assert len(result.valid_records) == 0

    duplicate_issues = [
        issue
        for issue in result.preview.issues
        if issue.code == "DUPLICATE_EXTERNAL_REF"
    ]

    assert len(duplicate_issues) == 2
    assert {
        issue.row_number for issue in duplicate_issues
    } == {2, 3}


def test_invalid_coordinates_are_rejected():
    content = csv_bytes(
        "external_ref,property_type,is_synthetic,latitude,longitude\n"
        "COL-001,villa,true,95,55\n"
    )

    result = validate_collateral_csv(content)

    assert result.preview.invalid_rows == 1
    assert result.valid_records == []


def test_coordinates_must_be_provided_together():
    content = csv_bytes(
        "external_ref,property_type,is_synthetic,latitude,longitude\n"
        "COL-001,villa,true,25.2,\n"
    )

    result = validate_collateral_csv(content)

    assert result.preview.invalid_rows == 1
    assert result.valid_records == []


def test_extra_values_in_row_are_rejected():
    content = csv_bytes(
        "external_ref,property_type,is_synthetic\n"
        "COL-001,villa,true,unexpected\n"
    )

    result = validate_collateral_csv(content)

    assert result.preview.invalid_rows == 1
    assert result.valid_records == []


def test_blank_rows_are_ignored():
    content = csv_bytes(
        "external_ref,property_type,is_synthetic\n"
        "COL-001,villa,true\n"
        "\n"
        "COL-002,apartment,false\n"
    )

    result = validate_collateral_csv(content)

    assert result.preview.total_rows == 2
    assert result.preview.valid_rows == 2


def test_non_bytes_input_is_rejected():
    with pytest.raises(TypeError):
        validate_collateral_csv(
            "external_ref,property_type,is_synthetic"
        )


def test_csv_with_utf8_bom_is_supported():
    content = (
        "\ufeffexternal_ref,property_type,is_synthetic\n"
        "COL-001,villa,true\n"
    ).encode("utf-8")

    result = validate_collateral_csv(content)

    assert result.preview.valid_rows == 1
    assert result.valid_records[0]["external_ref"] == "COL-001"
