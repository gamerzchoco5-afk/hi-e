"""One-to-one chat: message requests, conversations, messages, read receipts and reports.

Every endpoint here uses the chat database login (ChatDb), never the main one.
"""

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import String, case, column, func, or_, select, table, text
from sqlalchemy.exc import IntegrityError
from ..core.database import now
from ..models.chat import ChatReport, Conversation, Message
from ..models.identity import User
from ..schemas.chat import ChatReportInput, Read, Send, Start
from .deps import ChatDb, ChatMe, chat_quota

router = APIRouter()


def is_blocked(db, left, right):
    return bool(
        db.scalar(
            text(
                "SELECT 1 FROM blocks WHERE (blocker_id=:a AND blocked_id=:b) OR (blocker_id=:b AND blocked_id=:a) LIMIT 1"
            ),
            {"a": left, "b": right},
        )
    )


def get_conversation(db, identity, me, lock=False):
    stmt = select(Conversation).where(
        Conversation.id == identity,
        or_(Conversation.user_a == me["id"], Conversation.user_b == me["id"]),
    )
    if lock:
        stmt = stmt.with_for_update()
    c = db.scalar(stmt)
    if not c:
        raise HTTPException(404, "Conversation not found")
    peer = c.user_b if me["id"] == c.user_a else c.user_a
    active = db.scalar(select(User.id).where(User.id == peer, User.disabled.is_(False)))
    if not active or is_blocked(db, me["id"], peer):
        raise HTTPException(404, "Conversation not found")
    return c


def message_json(m, me):
    return {
        "id": m.id,
        "conversation_id": m.conversation_id,
        "sender_id": m.sender_id,
        "body": "" if m.deleted else m.body,
        "deleted": m.deleted,
        "is_me": m.sender_id == me["id"],
        "created_at": m.created_at,
        "client_id": m.client_id,
    }


@router.post("/v1/conversations", status_code=201)
def start(data: Start, request: Request, me: ChatMe, db: ChatDb):
    chat_quota(request, me, "chat-start", 10, 3600)
    peer = (
        db.execute(
            select(User.id, User.message_requests).where(
                User.username == data.username, User.disabled.is_(False)
            )
        )
        .mappings()
        .one_or_none()
    )
    if not peer or peer["id"] == me["id"] or is_blocked(db, me["id"], peer["id"]):
        raise HTTPException(404, "Profile not found")
    follows = bool(
        db.scalar(
            text("SELECT 1 FROM follows WHERE follower_id=:peer AND followed_id=:me"),
            {"peer": peer["id"], "me": me["id"]},
        )
    )
    a, b = sorted([me["id"], peer["id"]])
    existing = db.scalar(
        select(Conversation).where(Conversation.user_a == a, Conversation.user_b == b)
    )
    if existing:
        return {"id": existing.id}
    if not peer["message_requests"] and not follows:
        raise HTTPException(403, "This person is not accepting message requests")
    c = Conversation(user_a=a, user_b=b, starter_id=me["id"], accepted=follows)
    db.add(c)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        c = db.scalar(
            select(Conversation).where(
                Conversation.user_a == a, Conversation.user_b == b
            )
        )
        if not c:
            raise HTTPException(409, "Conversation changed; try again")
    return {"id": c.id}


@router.get("/v1/conversations")
def conversations(
    me: ChatMe,
    db: ChatDb,
    offset: int = Query(0, ge=0, le=10000),
    limit: int = Query(20, ge=1, le=50),
):
    block_table = table(
        "blocks", column("blocker_id", String), column("blocked_id", String)
    )
    hidden = (
        select(block_table.c.blocked_id)
        .where(block_table.c.blocker_id == me["id"])
        .union(
            select(block_table.c.blocker_id).where(block_table.c.blocked_id == me["id"])
        )
    )
    peers = select(User.id).where(User.disabled.is_(False), User.id.not_in(hidden))
    stmt = (
        select(Conversation)
        .where(
            or_(Conversation.user_a == me["id"], Conversation.user_b == me["id"]),
            Conversation.user_a.in_(peers),
            Conversation.user_b.in_(peers),
        )
        .order_by(Conversation.updated_at.desc(), Conversation.id)
        .offset(offset)
        .limit(limit + 1)
    )
    rows = list(db.scalars(stmt))
    page = rows[:limit]
    ids = [c.id for c in page]
    peer_ids = [c.user_b if c.user_a == me["id"] else c.user_a for c in page]
    peer_rows = db.execute(
        select(User.id, User.username, User.display_name, User.avatar_version).where(
            User.id.in_(peer_ids)
        )
    ).mappings()
    peer_map = {row["id"]: row for row in peer_rows}
    last_ids = (
        select(func.max(Message.id))
        .where(Message.conversation_id.in_(ids))
        .group_by(Message.conversation_id)
    )
    last_messages = {
        m.conversation_id: m
        for m in db.scalars(select(Message).where(Message.id.in_(last_ids)))
    }
    read_position = case(
        (Conversation.user_a == me["id"], Conversation.read_a),
        else_=Conversation.read_b,
    )
    unread = dict(
        db.execute(
            select(Message.conversation_id, func.count())
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(
                Message.conversation_id.in_(ids),
                Message.id > read_position,
                Message.sender_id != me["id"],
            )
            .group_by(Message.conversation_id)
        ).all()
    )
    items = []
    for c in page:
        peer = peer_map[c.user_b if c.user_a == me["id"] else c.user_a]
        last = last_messages.get(c.id)
        items.append(
            {
                "id": c.id,
                "username": peer["username"],
                "display_name": peer["display_name"],
                "avatar_version": peer["avatar_version"],
                "accepted": c.accepted,
                "is_request": not c.accepted and c.starter_id != me["id"],
                "unread_count": unread.get(c.id, 0),
                "last_message": message_json(last, me) if last else None,
            }
        )
    return {
        "items": items,
        "next_offset": offset + limit if len(rows) > limit else None,
    }


@router.get("/v1/conversations/{identity}/messages")
def messages(
    identity: str,
    me: ChatMe,
    db: ChatDb,
    after: int = Query(0, ge=0),
    before: int | None = Query(None, gt=0),
    limit: int = Query(40, ge=1, le=100),
):
    c = get_conversation(db, identity, me)
    stmt = select(Message).where(Message.conversation_id == c.id)
    if before:
        stmt = stmt.where(Message.id < before)
    if after:
        stmt = stmt.where(Message.id > after)
    rows = list(
        db.scalars(
            stmt.order_by(Message.id.asc() if after else Message.id.desc()).limit(
                limit + 1
            )
        )
    )
    page = rows[:limit]
    if not after:
        page.reverse()
    peer_id = c.user_b if c.user_a == me["id"] else c.user_a
    show = db.scalar(select(User.show_activity).where(User.id == peer_id))
    return {
        "items": [message_json(m, me) for m in page],
        "has_more": len(rows) > limit,
        "accepted": c.accepted,
        "is_request": not c.accepted and c.starter_id != me["id"],
        "peer_read": (c.read_b if c.user_a == me["id"] else c.read_a) if show else 0,
    }


@router.post("/v1/conversations/{identity}/messages", status_code=201)
def send(identity: str, data: Send, request: Request, me: ChatMe, db: ChatDb):
    chat_quota(request, me)
    c = get_conversation(db, identity, me, lock=True)
    existing = db.scalar(
        select(Message).where(
            Message.sender_id == me["id"], Message.client_id == data.client_id
        )
    )
    if existing:
        if existing.conversation_id != c.id:
            raise HTTPException(409, "This request ID belongs to another conversation")
        if not existing.deleted and existing.body != data.body:
            raise HTTPException(
                409,
                "This attempt already sent different content. Reopen this conversation before sending a new message.",
            )
        return message_json(existing, me)
    if not c.accepted:
        if c.starter_id != me["id"]:
            raise HTTPException(403, "Accept the message request first")
        if db.scalar(
            select(Message.id).where(Message.conversation_id == c.id).limit(1)
        ):
            raise HTTPException(403, "Wait for this person to accept your request")
    message = Message(
        conversation_id=c.id,
        sender_id=me["id"],
        body=data.body,
        client_id=data.client_id,
    )
    c.updated_at = now()
    db.add(message)
    db.commit()
    return message_json(message, me)


@router.put("/v1/conversations/{identity}/accept")
def accept(identity: str, request: Request, me: ChatMe, db: ChatDb):
    chat_quota(request, me)
    c = get_conversation(db, identity, me, lock=True)
    if c.starter_id == me["id"]:
        raise HTTPException(403, "Only the recipient can accept")
    c.accepted = True
    db.commit()
    return {"ok": True}


@router.put("/v1/conversations/{identity}/read")
def mark_read(identity: str, data: Read, request: Request, me: ChatMe, db: ChatDb):
    chat_quota(request, me, "chat-read", 60, 60)
    c = get_conversation(db, identity, me, lock=True)
    last = (
        db.scalar(select(func.max(Message.id)).where(Message.conversation_id == c.id))
        or 0
    )
    if data.message_id > last:
        raise HTTPException(422, "Invalid read position")
    if c.user_a == me["id"]:
        c.read_a = max(c.read_a, data.message_id)
    else:
        c.read_b = max(c.read_b, data.message_id)
    db.commit()
    return {"ok": True}


@router.delete("/v1/messages/{identity}")
def remove_message(identity: int, request: Request, me: ChatMe, db: ChatDb):
    chat_quota(request, me)
    message = db.get(Message, identity)
    if not message or message.sender_id != me["id"]:
        raise HTTPException(404, "Message not found")
    get_conversation(db, message.conversation_id, me)
    message.body = ""
    message.deleted = True
    db.commit()
    return {"ok": True}


@router.put("/v1/conversations/{identity}/report")
def report(identity: str, data: ChatReportInput, request: Request, me: ChatMe, db: ChatDb):
    chat_quota(request, me, "chat-report", 5, 3600)
    c = get_conversation(db, identity, me)
    if not db.get(ChatReport, (c.id, me["id"])):
        db.add(
            ChatReport(conversation_id=c.id, reporter_id=me["id"], reason=data.reason)
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
    return {"ok": True}
