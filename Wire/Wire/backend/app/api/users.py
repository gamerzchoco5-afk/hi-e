"""People: search, profiles, follow graph and blocking."""

from typing import Literal
from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import and_, delete, func, or_, select
from ..models.identity import User
from ..models.social import Block, Follow, Post
from ..services.serializers import page_posts, profile_json, profiles_json
from .deps import commit_unique, Db, Me, get_profile, hidden_ids, quota

router = APIRouter()


@router.get("/v1/users")
def search_users(
    me: Me,
    db: Db,
    q: str = Query("", max_length=50),
    cursor: str | None = Query(None, max_length=24),
    limit: int = Query(20, ge=1, le=50),
):
    stmt = select(User).where(User.disabled.is_(False), User.id.not_in(hidden_ids(me)))
    if q.strip():
        query = q.strip().lower().removeprefix("@")
        stmt = stmt.where(
            or_(
                User.username.contains(query, autoescape=True),
                func.lower(User.display_name).contains(query, autoescape=True),
            )
        )
    if cursor:
        stmt = stmt.where(User.username > cursor)
    users = list(db.scalars(stmt.order_by(User.username).limit(limit + 1)))
    return {
        "items": profiles_json(db, users[:limit], me),
        "next_cursor": users[limit - 1].username if len(users) > limit else None,
    }


@router.get("/v1/users/{username}")
def user_profile(username: str, me: Me, db: Db):
    return profile_json(db, get_profile(db, username, me), me)


@router.get("/v1/users/{username}/posts")
def user_posts(
    username: str,
    me: Me,
    db: Db,
    cursor: int | None = Query(None, gt=0),
    limit: int = Query(20, ge=1, le=50),
):
    user = get_profile(db, username, me)
    return page_posts(
        db,
        select(Post).where(Post.author_id == user.id, Post.parent_id.is_(None)),
        me,
        cursor,
        limit,
    )


@router.get("/v1/users/{username}/connections")
def connections(
    username: str,
    me: Me,
    db: Db,
    kind: Literal["followers", "following"] = "followers",
    cursor: str | None = Query(None, max_length=24),
    limit: int = Query(20, ge=1, le=50),
):
    user = get_profile(db, username, me)
    ids = (
        select(Follow.follower_id).where(Follow.followed_id == user.id)
        if kind == "followers"
        else select(Follow.followed_id).where(Follow.follower_id == user.id)
    )
    stmt = select(User).where(
        User.id.in_(ids), User.id.not_in(hidden_ids(me)), User.disabled.is_(False)
    )
    if cursor:
        stmt = stmt.where(User.username > cursor)
    users = list(db.scalars(stmt.order_by(User.username).limit(limit + 1)))
    return {
        "items": profiles_json(db, users[:limit], me),
        "next_cursor": users[limit - 1].username if len(users) > limit else None,
    }


@router.put("/v1/users/{username}/follow")
def follow(username: str, request: Request, me: Me, db: Db):
    quota(request, me, "follow", 30, 60)
    user = get_profile(db, username, me)
    if user.id == me.id:
        raise HTTPException(400, "You cannot follow yourself")
    if not db.get(Follow, (me.id, user.id)):
        db.add(Follow(follower_id=me.id, followed_id=user.id))
        commit_unique(db)
    return profile_json(db, user, me)


@router.delete("/v1/users/{username}/follow")
def unfollow(username: str, request: Request, me: Me, db: Db):
    quota(request, me, "follow", 30, 60)
    user = get_profile(db, username, me)
    db.execute(
        delete(Follow).where(Follow.follower_id == me.id, Follow.followed_id == user.id)
    )
    db.commit()
    return profile_json(db, user, me)


@router.get("/v1/blocks")
def blocks(
    me: Me,
    db: Db,
    cursor: str | None = Query(None, max_length=24),
    limit: int = Query(20, ge=1, le=50),
):
    stmt = select(User).where(
        User.id.in_(select(Block.blocked_id).where(Block.blocker_id == me.id))
    )
    if cursor:
        stmt = stmt.where(User.username > cursor)
    users = list(db.scalars(stmt.order_by(User.username).limit(limit + 1)))
    return {
        "items": [
            {"username": u.username, "display_name": u.display_name}
            for u in users[:limit]
        ],
        "next_cursor": users[limit - 1].username if len(users) > limit else None,
    }


@router.put("/v1/users/{username}/block")
def block_user(username: str, request: Request, me: Me, db: Db):
    quota(request, me)
    user = db.scalar(select(User).where(User.username == username.lower()))
    if not user:
        raise HTTPException(404, "Profile not found")
    if user.id == me.id:
        raise HTTPException(400, "You cannot block yourself")
    db.execute(
        delete(Follow).where(
            or_(
                and_(Follow.follower_id == me.id, Follow.followed_id == user.id),
                and_(Follow.follower_id == user.id, Follow.followed_id == me.id),
            )
        )
    )
    if not db.get(Block, (me.id, user.id)):
        db.add(Block(blocker_id=me.id, blocked_id=user.id))
    commit_unique(db)
    return {"ok": True}


@router.delete("/v1/users/{username}/block")
def unblock_user(username: str, request: Request, me: Me, db: Db):
    quota(request, me)
    user = db.scalar(select(User).where(User.username == username.lower()))
    if user:
        db.execute(
            delete(Block).where(Block.blocker_id == me.id, Block.blocked_id == user.id)
        )
        db.commit()
    return {"ok": True}
