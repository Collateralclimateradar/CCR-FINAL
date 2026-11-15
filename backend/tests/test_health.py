def test_health_ok_when_database_is_up(client_db_up):
    response = client_db_up.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["database"]["status"] == "up"
    assert body["app"]["name"] == "Climate Guard AI"
    assert "timestamp" in body


def test_health_reports_failure_when_database_is_down(client_db_down):
    response = client_db_down.get("/api/v1/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy"
    assert body["database"]["status"] == "down"


def test_health_does_not_leak_error_details(client_db_down):
    response = client_db_down.get("/api/v1/health")
    assert "secret-detail-123" not in response.text


def test_unknown_route_returns_404(client_db_up):
    assert client_db_up.get("/api/v1/does-not-exist").status_code == 404
