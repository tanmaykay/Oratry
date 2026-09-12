from app.db import SessionLocal
from app.services import process_job
def handle_attempt_analysis(attempt_id):
    with SessionLocal() as db: process_job(db,attempt_id)
