import logging
from rq import Queue
from app.redis_client import redis_client

q = Queue(connection=redis_client)

logger = logging.getLogger("weward_tasks")

def apply_to_advertiser_job(application_id: int):
    '''
    - Marks applications as approved asynchronously
    '''

    #lazy import to avoid circular import
    from app.app import app, db
    from app.models import Application

    with app.app_context():
        try:
            application = db.session.get(Application, application_id)
            if not application:
                logger.error("Application ID %s not found", application_id)
                return
            application.status = "approved"
            db.session.commit()
            logger.info("Application ID %s processed successfully", application_id)
        except Exception as e:
            db.session.rollback()
            logger.exception("Error processing application ID %s: %s", application_id, e)
