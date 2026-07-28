"""Tests for the Backoffice health endpoint."""


def test_health_returns_http_200(client):
    """The health endpoint reports a successful service status."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
