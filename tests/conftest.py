"""Фикстуры: у каждого теста своя временная БД (рабочие данные не затрагиваются)."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

PASSWORDS = {"admin": "admin-test-pass", "cook": "cook-test-pass", "economist": "econ-test-pass"}


def make_settings(tmp_path, demo_history=False) -> Settings:
    return Settings(
        app_env="test", database_url=f"sqlite:///{tmp_path / 'test.db'}", seed_on_startup=True,
        seed_demo_history=demo_history, cors_origins=("http://localhost:3000",),
        seed_admin_password=PASSWORDS["admin"], seed_cook_password=PASSWORDS["cook"],
        seed_economist_password=PASSWORDS["economist"])


@pytest.fixture()
def settings(tmp_path):
    return make_settings(tmp_path)


@pytest.fixture()
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture()
def demo_client(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, demo_history=True))) as c:
        yield c


def auth(client, username):
    r = client.post("/api/auth/login", json={"username": username, "password": PASSWORDS[username]})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


@pytest.fixture()
def admin(client):
    return auth(client, "admin")


@pytest.fixture()
def cook(client):
    return auth(client, "cook")


@pytest.fixture()
def economist(client):
    return auth(client, "economist")


@pytest.fixture()
def tomorrow():
    return (date.today() + timedelta(days=1)).isoformat()


def dish_ids(client) -> dict:
    return {d["slug"]: d["id"] for d in client.get("/api/menu").json()["data"]}


def ingredient_ids(client, headers) -> dict:
    return {i["slug"]: i["id"] for i in client.get("/api/ingredients", headers=headers).json()["data"]}


def stock_of(client, headers, slug) -> float:
    rows = client.get("/api/inventory", headers=headers).json()["data"]
    return next(r["stock_quantity"] for r in rows if r["slug"] == slug)


def place_order(client, items: dict, order_date, key=None, ids=None):
    """items: {slug: quantity}"""
    ids = ids or dish_ids(client)
    headers = {"Idempotency-Key": key} if key else {}
    body = {"order_date": order_date, "items": [{"dish_id": ids[s], "quantity": q} for s, q in items.items()]}
    return client.post("/api/orders", json=body, headers=headers)
