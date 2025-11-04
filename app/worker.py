import time
import logging
from sqlalchemy import text
from rq import Worker, Queue
from redis import Redis
import os
from sqlalchemy.exc import OperationalError
from app.app import app, db
from app.tasks import apply_to_advertiser_job

logger = logging.getLogger("weward_worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# ---------------- Connect to Redis ----------------
redis_url = f"redis://{os.getenv('REDIS_HOST', 'localhost')}:{os.getenv('REDIS_PORT', '6379')}"
redis_conn = Redis.from_url(redis_url)

try:
    redis_conn.ping()
    logger.info("Connected to Redis")
except Exception as e:
    logger.error("Redis connection failed: %s", e)
    raise

# ---------------- Ensure DB is ready ----------------
while True:
    try:
        with app.app_context():
            db.session.execute(text("SELECT 1"))
        logger.info("Database is ready")
        break
    except OperationalError:
        logger.info("Waiting for database to be ready...")
        time.sleep(1)

# ---------------- Start RQ Worker ----------------
q = Queue(name="default", connection=redis_conn)
worker = Worker([q], connection=redis_conn)
logger.info("Worker started, listening to queue...")
worker.work()
