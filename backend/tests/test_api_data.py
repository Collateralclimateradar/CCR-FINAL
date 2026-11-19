
def test_collateral_routes_require_authentication(client):
    """Every collateral endpoint must reject requests without a JWT."""
    org_id = make_org(client)

    # Remove the authenticated headers created by make_org.
    client.headers.clear()

    base_url = f"/api/v1/organizations/{org_id}/collaterals"
    collateral_id = str(uuid.uuid4())
    csv_file = {
        "file": (
            "collaterals.csv",
            (
                b"external_ref,property_type,is_synthetic\n"
                b"C-001,villa,true\n"
            ),
            "text/csv",
        )
    }

    requests = [
        client.get(base_url),
        client.post(
            base_url,
            json=COLLATERAL,
        ),
        client.get(f"{base_url}/{collateral_id}"),
        client.post(
            f"{base_url}/import/preview",
            files=csv_file,
        ),
        client.post(
            f"{base_url}/import",
            files=csv_file,
        ),
        client.get(
            f"{base_url}/{collateral_id}/valuations"
        ),
    ]

    for response in requests:
        assert response.status_code == 401, (
            f"Expected 401 but received {response.status_code}: "
            f"{response.text}"
        )
