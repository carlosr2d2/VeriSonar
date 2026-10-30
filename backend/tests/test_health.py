from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint_shape() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert "status" in payload
    assert payload["locale"] == "es"
    assert payload["processing_mode"] in {"offline", "online"}
    assert isinstance(payload["components"], list)
