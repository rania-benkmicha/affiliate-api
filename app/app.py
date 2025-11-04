from flask import Flask, request, jsonify
from redis import Redis
from rq import Queue
import json, os, hmac, hashlib
from app.models import db, Advertiser, Editor, Application, Order
from app.redis_client import redis_client
from app.tasks import apply_to_advertiser_job, q
import os


import logging

# ---------------- Logging ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("weward_app")


#---------------------------------------------

app = Flask(__name__)
os.makedirs("/app/data", exist_ok=True)
db_path = "/app/data/weward.db"
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "randomWord")


# ----------------------------------
def preload_sql_data():
    '''
    -Preloads data

    -Maps editors to eligible advertisers.

    -Clears Redis cache for fresh state.

    '''
    try:
        with app.app_context():
            db.create_all()

            # Advertisers table
            if not Advertiser.query.first():
                advertisers = [
                    Advertiser(id=1, name="Decathlon", category="Sport"),
                    Advertiser(id=2, name="Sephora", category="Beauty"),
                    Advertiser(id=3, name="Fnac", category="Electronics"),
                    Advertiser(id=4, name="Carrefour", category="Grocery"),
                    Advertiser(id=5, name="Amazon", category="E-commerce")
                ]
                db.session.add_all(advertisers)
                db.session.commit()

            # Editors table
            if not Editor.query.first():
                editors = [
                    Editor(id=42, name="Alice"),
                    Editor(id=43, name="Bob")
                ]
                db.session.add_all(editors)
                db.session.commit()

            #  ensure they exist in current session
            alice = Editor.query.get(42)
            bob = Editor.query.get(43)

            def safe_extend(editor, advertiser_ids):
                if not editor:
                    logger.warning("Editor not found when extending eligible advertisers.")
                    return
                for adv_id in advertiser_ids:
                    advertiser = Advertiser.query.get(adv_id)
                    if advertiser and advertiser not in editor.eligible_advertisers:
                        editor.eligible_advertisers.append(advertiser)

            # Assigning eligible advertisers for each editor
            safe_extend(alice, [1, 3, 4])
            safe_extend(bob, [2, 4])
            db.session.commit()

            redis_client.delete("applications")
            redis_client.delete("orders")
            redis_client.delete("advertisers_cache")
            logger.info("Preloaded SQL data and cleared Redis caches.")

    except Exception as e:
        logger.exception("Error in preload_sql_data: %s", e)



preload_sql_data()

# ---------------- Routes ----------------

@app.route("/", methods=["GET"])
def health():
    try:
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        logger.exception("Error in GET /: %s", e)
        return jsonify({"error": "Internal server error"}), 500
    



@app.route("/advertisers", methods=["GET"])
def get_advertisers():
    '''
    Retrieve eligible advertisers information
    '''
    try:
        editor_id = request.args.get("editor_id", type=int)

        # Try full list cache
        cached = redis_client.get("advertisers_cache")
        if cached:
            advertisers = json.loads(cached)
            logger.info("Fetched advertisers from cache.")
        else:
            advertisers = []
            for a in Advertiser.query.all():
                adv_dict = {"id": a.id, "name": a.name, "category": a.category}
                advertisers.append(adv_dict)
                redis_client.setex(f"advertiser:{a.id}", 3600, json.dumps(adv_dict))
            redis_client.setex("advertisers_cache", 3600, json.dumps(advertisers))
            logger.info("Fetched advertisers from SQL and cached results.")

        if editor_id:
            editor = Editor.query.get(editor_id)
            if editor:
                eligible_ids = [a.id for a in editor.eligible_advertisers]
                advertisers = [a for a in advertisers if a["id"] in eligible_ids]
                logger.info("Filtered advertisers by editor_id=%s", editor_id)
            else:
                advertisers = []

        return jsonify(advertisers), 200
    except Exception as e:
        logger.exception("Error in GET /advertisers: %s", e)
        return jsonify({"error": "Internal server error"}), 500
    

@app.route("/advertisers/<int:advertiser_id>", methods=["GET"])
def get_advertiser(advertiser_id):
    '''
    Retrieve eligible advertiser information
    '''
    try:
        editor_id = request.args.get("editor_id", type=int)

        cached = redis_client.get(f"advertiser:{advertiser_id}")
        if cached:
            advertiser = json.loads(cached)
            logger.info("Fetched advertiser id=%s from cache.", advertiser_id)
        else:
            adv_obj = Advertiser.query.get(advertiser_id)
            if not adv_obj:
                return jsonify({"error": "Advertiser not found"}), 404
            advertiser = {"id": adv_obj.id, "name": adv_obj.name, "category": adv_obj.category}
            redis_client.setex(f"advertiser:{advertiser_id}", 3600, json.dumps(advertiser))
            logger.info("Fetched advertiser id=%s from SQL and cached.", advertiser_id)

        if editor_id:
            editor = Editor.query.get(editor_id)
            if not editor or advertiser_id not in [a.id for a in editor.eligible_advertisers]:
                return jsonify({"error": "Not eligible for this advertiser"}), 403

        return jsonify(advertiser), 200
    except Exception as e:
        logger.exception("Error in GET /advertisers/%s: %s", advertiser_id, e)
        return jsonify({"error": "Internal server error"}), 500
    

@app.route("/applications", methods=["POST"])
def post_application():
    '''
    The goal of this function is to let the editor apply for an advertiser 
    '''
    try:
        data = request.get_json()
        advertiser_id = data.get("advertiser_id")
        editor_id = data.get("editor_id")
        if not advertiser_id or not editor_id:
            return jsonify({"error": "Missing advertiser_id or editor_id"}), 400

        editor = Editor.query.get(editor_id)
        advertiser = Advertiser.query.get(advertiser_id)
        if not editor or not advertiser or advertiser not in editor.eligible_advertisers:
            return jsonify({"error": "Not eligible"}), 403

        # Create application
        application = Application(
            advertiser_id=advertiser_id,
            editor_id=editor_id,
            status="pending"
        )
        db.session.add(application)
        db.session.commit()
        # Enqueue job (independent worker)
        job = q.enqueue(apply_to_advertiser_job, application.id)
        logger.info("Application created and job enqueued: id=%s", application.id)

        return jsonify({"job_id": job.get_id(), "status": "processing"}), 202
    except Exception as e:
        logger.exception("Error in POST /applications: %s", e)
        return jsonify({"error": "Internal server error"}), 500



@app.route("/applications", methods=["GET"])
def get_applications():
    try:
        applications = [
            {"advertiser_id": a.advertiser_id, "editor_id": a.editor_id, "status": a.status}
            for a in Application.query.all()
        ]
        return jsonify(applications), 200
    except Exception as e:
        logger.exception("Error in GET /applications: %s", e)
        return jsonify({"error": "Internal server error"}), 500

@app.route("/webhook/orders", methods=["POST"])
def webhook_orders():
    try:
        payload = request.get_json()
        sig = request.headers.get("X-Partner-Signature", "")
        expected_sig = hmac.new(WEBHOOK_SECRET.encode(), request.data, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return jsonify({"error": "Invalid signature"}), 401

        # Save to Redis
        orders = json.loads(redis_client.get("orders") or "[]")
        orders.append(payload)
        redis_client.set("orders", json.dumps(orders))

        # Save to SQL
        order = Order(
            order_id=payload["order_id"],
            advertiser_id=payload["advertiser_id"],
            editor_id=payload["user_id"],
            amount=payload["amount"],
            commission=payload["commission"]
        )
        db.session.add(order)
        db.session.commit()

        logger.info("Webhook order received and saved: order_id=%s", payload.get("order_id"))

        return jsonify({"status": "received"}), 200
    except Exception as e:
        logger.exception("Error in POST /webhook/orders: %s", e)
        return jsonify({"error": "Internal server error"}), 500


@app.route("/orders", methods=["GET"])
def get_orders():
    try:
        orders = json.loads(redis_client.get("orders") or "[]")
        return jsonify(orders), 200
    except Exception as e:
        logger.exception("Error in GET /orders: %s", e)
        return jsonify({"error": "Internal server error"}), 500
    

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
