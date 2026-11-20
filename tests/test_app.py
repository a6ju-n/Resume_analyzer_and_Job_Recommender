import pytest

from app import create_app
from config import TestConfig
from database.db import db
from database.models import User


@pytest.fixture
def client():
    app = create_app(TestConfig)
    with app.test_client() as c:
        yield c


def test_health(client):
    assert client.get("/health").get_json() == {"status": "ok"}


def test_landing_and_dashboard_render(client):
    assert b"Resume Analyzer" in client.get("/").data
    r = client.get("/dashboard/")
    assert r.status_code == 200 and b"No resumes yet" in r.data


def test_database_works(client):
    app = client.application
    with app.app_context():
        db.session.add(User(email="a@b.co", password_hash="x", full_name="A"))
        db.session.commit()
        assert User.query.count() == 1
