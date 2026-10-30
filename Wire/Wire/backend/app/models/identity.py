"""Account, session, avatar and rate-limit tables (Supabase schemas wire_identity / wire_security)."""

from sqlalchemy import Boolean, Date, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base, now, uid


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(40))
    date_of_birth: Mapped[object] = mapped_column(Date)
    bio: Mapped[str] = mapped_column(String(300), default="")
    pronouns: Mapped[str] = mapped_column(String(30), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    timed_out_until: Mapped[int] = mapped_column(Integer, default=0)
    avatar_version: Mapped[int] = mapped_column(Integer, default=0)
    message_requests: Mapped[bool] = mapped_column(Boolean, default=True)
    show_activity: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[int] = mapped_column(Integer, default=now)


class Session(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[int] = mapped_column(Integer, default=now)


class RecoveryCode(Base):
    __tablename__ = "recovery_codes"
    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )


class EmailChallenge(Base):
    __tablename__ = "email_challenges"
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[int] = mapped_column(Integer)


class Avatar(Base):
    __tablename__ = "avatars"
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    content: Mapped[bytes] = mapped_column(LargeBinary)


class RateBucket(Base):
    __tablename__ = "rate_buckets"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    bucket: Mapped[int] = mapped_column(Integer, primary_key=True)
    count: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[int] = mapped_column(Integer, index=True)
