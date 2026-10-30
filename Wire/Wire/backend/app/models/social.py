"""Posts, follows, likes, bookmarks, blocks and post reports (schema wire_main)."""

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column
from ..core.database import Base, now


class Post(Base):
    __tablename__ = "posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    author_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(10), default="note")
    title: Mapped[str] = mapped_column(String(160), default="")
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    client_id: Mapped[str] = mapped_column(String(36))
    __table_args__ = (
        UniqueConstraint("author_id", "client_id", name="post_client_unique"),
        CheckConstraint("kind IN ('note','article')", name="valid_post_kind"),
        Index("ix_posts_feed", "parent_id", "id"),
    )


class Follow(Base):
    __tablename__ = "follows"
    follower_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    followed_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    __table_args__ = (
        CheckConstraint("follower_id <> followed_id", name="no_self_follow"),
    )


class Like(Base):
    __tablename__ = "likes"
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class Bookmark(Base):
    __tablename__ = "bookmarks"
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class Block(Base):
    __tablename__ = "blocks"
    blocker_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    blocked_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    __table_args__ = (
        CheckConstraint("blocker_id <> blocked_id", name="no_self_block"),
    )


class Report(Base):
    __tablename__ = "reports"
    reporter_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )
    reason: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[int] = mapped_column(Integer, default=now)
