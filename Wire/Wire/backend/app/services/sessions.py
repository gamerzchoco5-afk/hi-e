"""Session issuing for sign-in, registration, recovery and password change."""

import secrets
from sqlalchemy import delete, select
from ..core.config import settings
from ..core.database import now
from ..core.security import digest
from ..models.identity import Session, User
from .serializers import profile_json

cfg = settings()


def issue_session(db, user):
    db.scalar(select(User.id).where(User.id == user.id).with_for_update())
    # Trim expired sessions and cap active devices to 10 per account.
    db.execute(
        delete(Session).where(Session.user_id == user.id, Session.expires_at <= now())
    )
    active = list(
        db.scalars(
            select(Session)
            .where(Session.user_id == user.id)
            .order_by(Session.created_at.desc())
        )
    )
    for old in active[9:]:
        db.delete(old)
    token = secrets.token_urlsafe(32)
    expires = now() + cfg.session_days * 86400
    db.add(Session(token_hash=digest(token), user_id=user.id, expires_at=expires))
    db.commit()
    return {
        "token": token,
        "expires_at": expires,
        "user": {**profile_json(db, user, user), "email_verified": user.email_verified},
    }
