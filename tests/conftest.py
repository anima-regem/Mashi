import pytest
from fastapi.testclient import TestClient

from mashi.app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "data", testing=True)
    with TestClient(app) as client:
        session = client.get("/api/session").json()
        client.headers["x-mashi-token"] = session["token"]
        yield client
