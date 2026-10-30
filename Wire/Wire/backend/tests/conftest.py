import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os
import tempfile

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = (
    "sqlite:///" + tempfile.mkdtemp(prefix="wire-tests-") + "/db.sqlite"
)
os.environ["RATE_LIMITS_ENABLED"] = "false"
os.environ["EMAIL_CODE_PEPPER"] = "test-only-pepper-never-use-in-production-0123456789"
import pytest
from fastapi.testclient import TestClient
from app.core.database import Base, SessionLocal, engine
from app.models.identity import User
from app.main import app
from sqlalchemy import select


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def main():
    with TestClient(app) as client:
        yield client


@pytest.fixture
def chat(main):
    # One application now serves both halves; the fixture keeps the old test names.
    return main


def signup(client, name="alice", verify=True):
    response = client.post(
        "/v1/auth/register",
        json={
            "username": name,
            "email": name + "@example.org",
            "password": "my-secure-password-914",
            "display_name": name.title(),
            "date_of_birth": "2000-03-09",
        },
    )
    assert response.status_code == 201, response.text
    value = response.json()
    if verify:
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.username == name))
            user.email_verified = True
            db.commit()
    return {"Authorization": "Bearer " + value["token"]}, value
