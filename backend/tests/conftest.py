import os

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/copilot-test-bootstrap.db")
os.environ["DEMO_ENABLED"] = "true"
os.environ["AI_PROVIDER"] = "offline"
os.environ["PUBLIC_ORIGIN"] = "http://localhost:5173"

import pytest
from fastapi.testclient import TestClient
from app.config import settings
from app.db import Base, engine, session_factory
from app.models import Staff
from app.main import app
from app.security import hash_password


@pytest.fixture(autouse=True)
def database(tmp_path, monkeypatch):
    url = os.getenv("TEST_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    if os.getenv("TEST_DATABASE_URL") and not url.rstrip("/").endswith("copilot_test"):
        raise RuntimeError(
            "Destructive test setup is restricted to the copilot_test database"
        )
    monkeypatch.setenv("DATABASE_URL", url)
    settings.cache_clear()
    engine.cache_clear()
    Base.metadata.drop_all(engine())
    Base.metadata.create_all(engine())
    with session_factory()() as db, db.begin():
        for login, role, servers in [
            ("admin", "admin", []),
            ("operator", "operator", ["Сервер 01"]),
            ("other", "operator", ["Сервер 02"]),
        ]:
            db.add(
                Staff(
                    login=login,
                    name=login,
                    role=role,
                    servers=servers,
                    password_hash=hash_password("TestPassword-123!"),
                )
            )
    yield
    engine().dispose()
    engine.cache_clear()
    settings.cache_clear()


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


@pytest.fixture
def admin(client):
    response = client.post(
        "/api/auth/login", json={"login": "admin", "password": "TestPassword-123!"}
    )
    assert response.status_code == 200
    client.headers["x-csrf-token"] = response.json()["csrf"]
    return client


@pytest.fixture
def complaint(admin):
    response = admin.post(
        "/api/demo/tickets",
        json={
            "nickname": "Alex_Walker",
            "server": "Сервер 01",
            "text": "Игрок обманул меня при обмене автомобилями, прошу проверить.",
            "category": "player",
        },
    )
    assert response.status_code == 200
    return response.json()
