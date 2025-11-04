import json
import pytest
from app.app import app, db, preload_sql_data
from app.models import Advertiser, Editor, Application, Order
from app.redis_client import redis_client
from app.tasks import q
import hmac
import hashlib


# ---------------------- Fixture ----------------------
@pytest.fixture
def client():
    # Reset DB for tests
    with app.app_context():
        db.drop_all()
        db.create_all()
        preload_sql_data()

        # Ensure advertiser/editor eligibility
        advertiser = db.session.get(Advertiser, 1)
        editor = db.session.get(Editor, 42)
        if advertiser and editor:
            with db.session.no_autoflush:
                if hasattr(advertiser, "eligible_editors"):
                    if editor not in advertiser.eligible_editors:
                        advertiser.eligible_editors.append(editor)
                elif hasattr(advertiser, "is_active"):
                    advertiser.is_active = True
                else:
                    advertiser.editor_id = editor.id
            db.session.commit()

    # Flush Redis keys to start clean
    redis_client.flushall()
    with app.test_client() as client_app:
        yield client_app, redis_client, q


# ---------------------- Tests ----------------------

def test_health(client):
    client_app, _, _ = client
    res = client_app.get("/")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "ok"


def test_get_advertisers_cache(client):
    client_app, _, _ = client
    res = client_app.get("/advertisers")
    assert res.status_code == 200
    data = res.get_json()
    assert isinstance(data, list)
    assert len(data) == 5
    res2 = client_app.get("/advertisers")
    data2 = res2.get_json()
    assert data2 == data


def test_get_single_advertiser(client):
    client_app, _, _ = client
    with app.app_context():
        alice = db.session.get(Editor, 42)
        assert alice.name == "Alice"
    res = client_app.get("/advertisers/1?editor_id=42")
    assert res.status_code == 200
    data = res.get_json()
    assert data["id"] == 1
    assert data["name"] == "Decathlon"
    res = client_app.get("/advertisers/2?editor_id=42")
    assert res.status_code == 403



def test_webhook_orders(client):
    client_app, redis_conn, _ = client
    payload = {
        "order_id": "ORD1001",
        "advertiser_id": 1,
        "user_id": 42,
        "amount": 120.5,
        "commission": 6.2
    }
    payload_json = json.dumps(payload)
    sig = hmac.new("randomWord".encode(), payload_json.encode(), hashlib.sha256).hexdigest()
    res = client_app.post(
        "/webhook/orders",
        data=payload_json,
        headers={"X-Partner-Signature": sig, "Content-Type": "application/json"}
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "received"
    # Check DB
    with app.app_context():
        order_in_db = Order.query.filter_by(order_id="ORD1001").first()
        assert order_in_db is not None
        assert order_in_db.amount == 120.5
    # Check Redis
    redis_orders = json.loads(redis_conn.get("orders") or "[]")
    assert any(o["order_id"] == "ORD1001" for o in redis_orders)


def test_get_applications(client):
    client_app, _, _ = client
    with app.app_context():
        application = Application(advertiser_id=3, editor_id=42, status="approved")
        db.session.add(application)
        db.session.commit()
    res = client_app.get("/applications")
    assert res.status_code == 200
    apps = res.get_json()
    assert any(a["advertiser_id"] == 3 and a["editor_id"] == 42 for a in apps)


def test_webhook_invalid_signature(client):
    client_app, _, _ = client
    payload = {"order_id": "ORD999"}
    payload_json = json.dumps(payload)
    res = client_app.post(
        "/webhook/orders",
        data=payload_json,
        headers={"X-Partner-Signature": "wrong_sig", "Content-Type": "application/json"}
    )
    assert res.status_code == 401
    data = res.get_json()
    assert "error" in data
