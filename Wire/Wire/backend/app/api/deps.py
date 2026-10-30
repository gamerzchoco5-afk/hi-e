"""Shared request dependencies.

Account/social endpoints use the main database login (`Db`, `Me`).
Chat endpoints use the chat database login (`ChatDb`, `ChatMe`).
"""

from typing import Annotated
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession
from ..core.database import get_chat_db, get_db, now
from ..core.security import digest, limiter
from ..models.identity import Session, User
from ..models.social import Block, Post

Db = Annotated[DBSession, Depends(get_db)]
bearer = HTTPBearer(auto_error=False)


def unauthorized():
    return HTTPException(
        401, "Please sign in again", headers={"WWW-Authenticate": "Bearer"}
    )


def current_user(
    request: Request,
    db: Db,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    if not credentials or len(credentials.credentials) > 100:
        raise unauthorized()
    session = db.get(Session, digest(credentials.credentials))
    if not session or session.expires_at <= now():
        raise unauthorized()
    limiter.check("authenticated:" + session.user_id, 120, 60)
    user = db.get(User, session.user_id)
    if not user or user.disabled:
        raise unauthorized()
    if user.timed_out_until > now():
        raise HTTPException(
            423,
            "Account is temporarily restricted",
            headers={"Retry-After": str(user.timed_out_until - now())},
        )
    safe_paths = {
        "/v1/me",
        "/v1/auth/logout",
        "/v1/auth/logout-all",
        "/v1/auth/email/send",
        "/v1/auth/email/verify",
        "/v1/auth/password",
        "/v1/auth/recovery-codes",
    }
    if not user.email_verified and request.url.path not in safe_paths:
        raise HTTPException(403, "Verify your email first")
    return user


Me = Annotated[User, Depends(current_user)]


def quota(request, user=None, group="write", cap=30, window=60):
    # X-Forwarded-For is deliberately not trusted here. Configure a trusted proxy at deployment.
    ip = request.client.host if request.client else "unknown"
    limiter.check(group + ":ip:" + ip, cap * 3 if user else cap, window)
    if user:
        limiter.check(group + ":user:" + user.id, cap, window)


def hidden_ids(me):
    return (
        select(Block.blocked_id)
        .where(Block.blocker_id == me.id)
        .union(select(Block.blocker_id).where(Block.blocked_id == me.id))
    )


def blocked(db, left, right):
    return bool(
        db.scalar(
            select(
                exists().where(
                    or_(
                        and_(Block.blocker_id == left, Block.blocked_id == right),
                        and_(Block.blocker_id == right, Block.blocked_id == left),
                    )
                )
            )
        )
    )


def get_profile(db, username, me):
    user = db.scalar(
        select(User).where(User.username == username.lower(), User.disabled.is_(False))
    )
    if not user or blocked(db, me.id, user.id):
        raise HTTPException(404, "Profile not found")
    return user


def get_post(db, post_id, me):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Post not found")
    author = db.get(User, post.author_id)
    if not author or author.disabled or blocked(db, me.id, post.author_id):
        raise HTTPException(404, "Post not found")
    # Protect a reply whose parent is hidden as well.
    if post.parent_id:
        parent = db.get(Post, post.parent_id)
        parent_author = db.get(User, parent.author_id) if parent else None
        if (
            not parent
            or not parent_author
            or parent_author.disabled
            or blocked(db, me.id, parent.author_id)
        ):
            raise HTTPException(404, "Post not found")
    return post


def commit_unique(db):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if getattr(exc.orig, "sqlstate", None) != "23505" and getattr(
            exc.orig, "sqlite_errorcode", None
        ) not in (1555, 2067):
            raise HTTPException(409, "This resource changed. Refresh and try again.")
        # A concurrent identical PUT already created the same unique relation.

# ---------------------------------------------------------------- chat side
ChatDb = Annotated[DBSession, Depends(get_chat_db)]


def chat_current_user(
    db: ChatDb,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    # The chat login can read only the identity columns selected here.
    if not credentials or len(credentials.credentials) > 100:
        raise HTTPException(401, "Please sign in again")
    session = db.get(Session, digest(credentials.credentials))
    if not session or session.expires_at <= now():
        raise HTTPException(401, "Please sign in again")
    limiter.check("authenticated:" + session.user_id, 120, 60)
    user = (
        db.execute(
            select(
                User.id,
                User.username,
                User.display_name,
                User.disabled,
                User.timed_out_until,
                User.email_verified,
            ).where(User.id == session.user_id)
        )
        .mappings()
        .one_or_none()
    )
    if not user or user["disabled"]:
        raise HTTPException(401, "Please sign in again")
    if user["timed_out_until"] > now():
        raise HTTPException(
            423,
            "Account is temporarily restricted",
            headers={"Retry-After": str(user["timed_out_until"] - now())},
        )
    if not user["email_verified"]:
        raise HTTPException(403, "Verify your email first")
    return user


ChatMe = Annotated[dict, Depends(chat_current_user)]


def chat_quota(request, me, group="chat-write", cap=30, seconds=60):
    ip = request.client.host if request.client else "unknown"
    limiter.check(group + ":ip:" + ip, cap * 3, seconds)
    limiter.check(group + ":user:" + me["id"], cap, seconds)
