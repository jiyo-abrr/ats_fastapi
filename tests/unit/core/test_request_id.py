from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_generates_a_request_id_when_none_supplied():
    resp = client.get("/health")
    assert resp.status_code == 200
    request_id = resp.headers.get("X-Request-ID")
    assert request_id
    assert len(request_id) == 36  # a UUID4 string


def test_echoes_a_caller_supplied_request_id():
    resp = client.get("/health", headers={"X-Request-ID": "caller-supplied-id"})
    assert resp.headers.get("X-Request-ID") == "caller-supplied-id"


def test_different_requests_get_different_ids():
    a = client.get("/health").headers["X-Request-ID"]
    b = client.get("/health").headers["X-Request-ID"]
    assert a != b
