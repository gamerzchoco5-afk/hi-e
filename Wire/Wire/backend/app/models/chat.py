"""Conversations, messages and chat reports (schema wire_chat)."""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from ..core.database import Base, now, uid


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_a: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    user_b: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    starter_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    read_a: Mapped[int] = mapped_column(Integer, default=0)
    read_b: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[int] = mapped_column(Integer, default=now, index=True)
    __table_args__ = (
        UniqueConstraint("user_a", "user_b"),
        CheckConstraint("user_a < user_b", name="ordered_pair"),
    )


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    sender_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    client_id: Mapped[str] = mapped_column(String(36))
    body: Mapped[str] = mapped_column(Text)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    __table_args__ = (
        UniqueConstraint("sender_id", "client_id"),
        Index("ix_messages_page", "conversation_id", "id"),
        Index("ix_messages_sender", "sender_id"),
    )


class ChatReport(Base):
    __tablename__ = "chat_reports"
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )
    reporter_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    reason: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[int] = mapped_column(Integer, default=now)
