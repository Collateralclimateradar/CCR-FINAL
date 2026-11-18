
def test_preview_duplicate_external_refs_marks_both_rows_invalid(api_client):
    client, _ = api_client
    organization_id = create_organization(client)

    csv_content = (
        b"external_ref,property_type,is_synthetic\n"
        b"C-001,villa,true\n"
        b"C-001,apartment,true\n"
    )

    response = upload_csv(
        client,
        preview_url(organization_id),
        csv_content,
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["total_rows"] == 2
    assert data["valid_rows"] == 0
    assert data["invalid_rows"] == 2
    assert all(not row["is_valid"] for row in data["rows"])

    duplicate_issues = [
        issue
        for issue in data["issues"]
        if issue["code"] == "DUPLICATE_EXTERNAL_REF"
    ]

    assert len(duplicate_issues) == 2


def test_preview_rejects_more_than_10000_rows(api_client):
    client, _ = api_client
    organization_id = create_organization(client)

    header = "external_ref,property_type,is_synthetic\n"
    rows = "".join(
        f"C-{number},villa,true\n"
        for number in range(1, 10002)
    )

    response = upload_csv(
        client,
        preview_url(organization_id),
        (header + rows).encode("utf-8"),
    )

    assert response.status_code == 422
    assert "detail" in response.json()


def test_preview_malformed_csv_returns_422(api_client):
    client, _ = api_client
    organization_id = create_organization(client)

    csv_content = (
        b"external_ref,property_type,is_synthetic\n"
        b'"C-001,villa,true\n'
    )

    response = upload_csv(
        client,
        preview_url(organization_id),
        csv_content,
    )

    assert response.status_code == 422
    assert "detail" in response.json()
