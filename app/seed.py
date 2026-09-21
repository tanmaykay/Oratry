"""Idempotent development data for the SQLite FastAPI preview."""

from sqlalchemy import select

from app.core import password_hash
from app.db import SessionLocal
from app.models import Assignment, Challenge, User, VocabularyItem
from app.personalization.catalog import PRACTICE_CATALOG
from app.services import CurriculumService


def main() -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "maya@example.test"))
        if user is None:
            user = User(
                email="maya@example.test",
                password_hash=password_hash.hash("local-preview-password"),
                accepted_terms=True,
                preferences={"timezone": "Asia/Kolkata"},
            )
            db.add(user)
            db.flush()

        curriculum = CurriculumService(db)
        for candidate in PRACTICE_CATALOG:
            curriculum._ensure_challenge(candidate)
        challenge = db.get(Challenge, PRACTICE_CATALOG[0].id)

        if db.scalar(select(Assignment).where(Assignment.user_id == user.id)) is None:
            db.add(Assignment(user_id=user.id, challenge_id=challenge.id, reason="local_preview"))
        if db.scalar(select(VocabularyItem).where(VocabularyItem.user_id == user.id)) is None:
            db.add(VocabularyItem(user_id=user.id, word="concise", practice_status="learning"))
        db.commit()
    print("Seeded local preview user: maya@example.test / local-preview-password")


if __name__ == "__main__":
    main()
