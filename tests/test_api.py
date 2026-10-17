import asyncio
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.auth import get_session
from app.infrastructure.database import Base, UserRecord
from app.domain.exceptions import RuleViolation
from app.infrastructure.relational_inventory_repository import SqlAlchemyInventoryRepository
from app.main import app


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, record):
        del record
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def seed_catalog(repository):
    repository.save("branches", {"id": "b1", "name": "Main", "code": "M1", "city": "City", "phone": "123"})
    repository.save("brands", {"id": "brand1", "name": "Brand", "origin": "Local"})
    repository.save("categories", {"id": "category1", "name": "Parts", "description": "Parts"})
    repository.save("subcategories", {"id": "subcategory1", "name": "General", "category_id": "category1"})
    repository.save("customers", {"id": "c1", "name": "Customer", "phone": "", "email": "", "city": "", "address": ""})
    repository.save("vendors", {"id": "v1", "name": "Vendor", "phone": "", "email": "", "city": ""})
    repository.save("products", {
        "id": "p1", "sku": "PART-1", "name": "Part", "brand_id": "brand1",
        "category_id": "category1", "subcategory_id": "subcategory1", "gst": 18,
        "cost_price": 4, "selling_price": 8,
    })


def test_login_jwt_and_protected_inventory(session_factory):
    with session_factory() as session:
        session.add(UserRecord(id="u1", name="Test Admin", username="admin", password_hash=PasswordHash.recommended().hash("secret"), role="Admin", active=True))
        session.commit()

    def override_session():
        with session_factory() as session:
            yield session
            session.commit()

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            assert client.get("/api/inventory/branches").status_code == 401
            response = client.post("/api/auth/login", json={"username": "admin", "password": "secret"})
            assert response.status_code == 200
            token = response.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            created = client.post("/api/inventory/branches", headers=headers, json={"name": "Main", "code": "M1", "city": "City", "phone": "123"})
            assert created.status_code == 200
            assert created.json()["name"] == "Main"
            assert "password" not in created.json()
    finally:
        app.dependency_overrides.clear()


def test_user_password_update_is_persisted_and_usable_for_login(session_factory):
    with session_factory() as session:
        session.add(UserRecord(
            id="u1",
            name="Test Admin",
            username="admin",
            password_hash=PasswordHash.recommended().hash("old-secret"),
            role="Admin",
            active=True,
        ))
        session.commit()

    def override_session():
        with session_factory() as session:
            yield session
            session.commit()

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            login = client.post("/api/auth/login", json={"username": "admin", "password": "old-secret"})
            assert login.status_code == 200
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            updated = client.put(
                "/api/inventory/users/u1",
                headers=headers,
                json={
                    "name": "Test Admin",
                    "username": "admin",
                    "password": "new-secret",
                    "role": "Admin",
                    "active": True,
                },
            )
            assert updated.status_code == 200

            with session_factory() as session:
                stored_hash = session.get(UserRecord, "u1").password_hash
                assert stored_hash != "new-secret"
                assert PasswordHash.recommended().verify("new-secret", stored_hash)

            assert client.post(
                "/api/auth/login",
                json={"username": "admin", "password": "new-secret"},
            ).status_code == 200
            assert client.post(
                "/api/auth/login",
                json={"username": "admin", "password": "old-secret"},
            ).status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_session_is_committed_before_response_is_sent(session_factory):
    with session_factory() as session:
        session.add(UserRecord(id="u1", name="Test Admin", username="admin", password_hash=PasswordHash.recommended().hash("secret"), role="Admin", active=True))
        session.commit()
    events = []

    def override_session():
        with session_factory() as session:
            yield session
            session.commit()
            events.append("commit")

    async def call_login():
        body = b'{"username": "admin", "password": "secret"}'
        sent = False

        async def receive():
            nonlocal sent
            if sent:
                return {"type": "http.disconnect"}
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            if message["type"] == "http.response.body" and not message.get("more_body"):
                events.append("response")

        await app({
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
            "path": "/api/auth/login", "raw_path": b"/api/auth/login", "query_string": b"",
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
            "scheme": "http", "server": ("test", 80), "client": ("test", 1),
        }, receive, send)

    app.dependency_overrides[get_session] = override_session
    try:
        asyncio.run(call_login())
    finally:
        app.dependency_overrides.clear()
    assert events == ["commit", "response"]


def test_create_user_handles_blank_branch_and_rejects_bad_input(session_factory):
    with session_factory() as session:
        session.add(UserRecord(id="u1", name="Test Admin", username="admin", password_hash=PasswordHash.recommended().hash("secret"), role="Admin", active=True))
        SqlAlchemyInventoryRepository(session).save("branches", {"id": "br1", "name": "Main", "code": "M1", "city": "", "phone": ""})
        session.commit()

    def override_session():
        with session_factory() as session:
            yield session
            session.commit()

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            token = client.post("/api/auth/login", json={"username": "admin", "password": "secret"}).json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            def create(**overrides):
                body = {"name": "New", "username": "new1", "password": "pw", "role": "Manager", "branchId": "br1", "active": True}
                return client.post("/api/inventory/users", headers=headers, json={**body, **overrides})

            assert create().status_code == 200
            blank = create(username="admin2", role="Admin", branchId="")
            assert blank.status_code == 200
            assert blank.json()["branchId"] is None
            assert create().status_code == 409
            assert create(username="other", branchId="missing").status_code == 400
            assert create(username="other", role="superuser").status_code == 422

            assert client.post("/api/auth/login", json={"username": "admin2", "password": "pw"}).status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_sale_stock_is_atomic_on_insufficient_quantity(session_factory):
    with session_factory() as session:
        repository = SqlAlchemyInventoryRepository(session)
        seed_catalog(repository)
        repository.save("stock", {"id": "stock-1", "product_id": "p1", "branch_id": "b1", "quantity": 3}, "b1:p1")
        session.commit()
        sale = {"id": "sale-1", "number": "INV-1", "customer_id": "c1", "branch_id": "b1", "date": datetime.now(UTC).isoformat(), "items": [{"product_id": "p1", "quantity": 2, "unit_price": 8, "unit_cost": 4}]}
        repository.create_sale(sale)
        session.commit()
        assert repository.stock_item("p1", "b1")["quantity"] == 1
        sale["id"] = "sale-2"
        sale["number"] = "INV-2"
        sale["items"][0]["quantity"] = 2
        with pytest.raises(RuleViolation):
            repository.create_sale(sale)
        session.rollback()
        assert repository.stock_item("p1", "b1")["quantity"] == 1


def test_receipt_and_return_stock_movements_and_duplicate_line_limits(session_factory):
    with session_factory() as session:
        repository = SqlAlchemyInventoryRepository(session)
        seed_catalog(repository)
        repository.save("purchase_orders", {
            "id": "po1", "number": "PO-1", "vendor_id": "v1", "branch_id": "b1",
            "date": datetime.now(UTC).isoformat(), "expected_date": datetime.now(UTC).isoformat(),
            "status": "Pending", "payment_status": "Unpaid",
            "items": [{"product_id": "p1", "quantity": 5, "received": 0, "unit_cost": 4}],
        })
        session.commit()

        invalid_receipt = {
            "id": "grn-bad", "number": "GRN-BAD", "purchase_order_id": "po1",
            "date": datetime.now(UTC).isoformat(), "note": "", "items": [
                {"product_id": "p1", "quantity": 3}, {"product_id": "p1", "quantity": 3},
            ],
        }
        with pytest.raises(RuleViolation):
            repository.create_receipt(invalid_receipt)
        assert repository.stock_item("p1", "b1") is None

        receipt = {**invalid_receipt, "id": "grn1", "number": "GRN-1", "items": [{"product_id": "p1", "quantity": 5}]}
        repository.create_receipt(receipt)
        sale = {
            "id": "sale1", "number": "INV-1", "customer_id": "c1", "branch_id": "b1",
            "date": datetime.now(UTC).isoformat(),
            "items": [{"product_id": "p1", "quantity": 3, "unit_price": 8, "unit_cost": 4}],
        }
        repository.create_sale(sale)
        invalid_return = {
            "id": "return-bad", "number": "SR-BAD", "sale_id": "sale1",
            "date": datetime.now(UTC).isoformat(), "reason": "", "items": [
                {"product_id": "p1", "quantity": 2}, {"product_id": "p1", "quantity": 2},
            ],
        }
        with pytest.raises(RuleViolation):
            repository.create_return(invalid_return)
        assert repository.stock_item("p1", "b1")["quantity"] == 2

        repository.create_return({**invalid_return, "id": "return1", "number": "SR-1", "items": [{"product_id": "p1", "quantity": 1}]})
        transaction_types = {transaction["type"] for transaction in repository.list("transactions")}
        assert transaction_types == {"Purchase", "Sale", "Return"}
        assert repository.stock_item("p1", "b1")["quantity"] == 3