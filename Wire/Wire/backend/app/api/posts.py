"""Feed, posts, replies, likes, bookmarks and post reports."""

from typing import Literal
from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from ..models.social import Bookmark, Follow, Like, Post, Report
from ..schemas.accounts import PostCreate, ReportInput
from ..services.serializers import page_posts, posts_json
from .deps import commit_unique, Db, Me, get_post, quota

router = APIRouter()


@router.get("/v1/feed")
def feed(
    me: Me,
    db: Db,
    mode: Literal["discover", "following"] = "discover",
    cursor: int | None = Query(None, gt=0),
    limit: int = Query(20, ge=1, le=50),
):
    q = select(Post).where(Post.parent_id.is_(None))
    if mode == "following":
        q = q.where(
            or_(
                Post.author_id == me.id,
                Post.author_id.in_(
                    select(Follow.followed_id).where(Follow.follower_id == me.id)
                ),
            )
        )
    return page_posts(db, q, me, cursor, limit)


@router.post("/v1/posts", status_code=201)
def create_post(data: PostCreate, request: Request, me: Me, db: Db):
    quota(request, me, "post", 10, 60)
    if data.parent_id:
        parent = get_post(db, data.parent_id, me)
        # Flat reply threads keep queries, moderation and navigation bounded.
        if parent.parent_id:
            raise HTTPException(400, "Reply to the original post")
    existing = db.scalar(
        select(Post).where(Post.author_id == me.id, Post.client_id == data.client_id)
    )
    if existing:
        if any(
            getattr(existing, key) != value
            for key, value in data.model_dump(exclude={"client_id"}).items()
        ):
            raise HTTPException(
                409,
                "This attempt already published different content. Check your profile before starting a new post.",
            )
        return posts_json(db, [get_post(db, existing.id, me)], me)[0]
    post = Post(author_id=me.id, **data.model_dump())
    db.add(post)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        post = db.scalar(
            select(Post).where(
                Post.author_id == me.id, Post.client_id == data.client_id
            )
        )
        if not post or any(
            getattr(post, key) != value
            for key, value in data.model_dump(exclude={"client_id"}).items()
        ):
            raise HTTPException(
                409,
                "This attempt already published different content. Check your profile.",
            )
    return posts_json(db, [post], me)[0]


@router.get("/v1/posts/{post_id}")
def post_detail(post_id: int, me: Me, db: Db):
    return posts_json(db, [get_post(db, post_id, me)], me)[0]


@router.delete("/v1/posts/{post_id}")
def remove_post(post_id: int, request: Request, me: Me, db: Db):
    quota(request, me)
    post = get_post(db, post_id, me)
    if post.author_id != me.id:
        raise HTTPException(403, "Only the author can delete this post")
    db.delete(post)
    db.commit()
    return {"ok": True}


@router.get("/v1/posts/{post_id}/replies")
def replies(
    post_id: int,
    me: Me,
    db: Db,
    cursor: int | None = Query(None, gt=0),
    limit: int = Query(20, ge=1, le=50),
):
    get_post(db, post_id, me)
    return page_posts(
        db, select(Post).where(Post.parent_id == post_id), me, cursor, limit
    )


@router.put("/v1/posts/{post_id}/like")
def like_post(post_id: int, request: Request, me: Me, db: Db):
    quota(request, me, "reaction", 60, 60)
    post = get_post(db, post_id, me)
    if not db.get(Like, (me.id, post.id)):
        db.add(Like(user_id=me.id, post_id=post.id))
        commit_unique(db)
    return posts_json(db, [post], me)[0]


@router.delete("/v1/posts/{post_id}/like")
def unlike_post(post_id: int, request: Request, me: Me, db: Db):
    quota(request, me, "reaction", 60, 60)
    post = get_post(db, post_id, me)
    db.execute(delete(Like).where(Like.user_id == me.id, Like.post_id == post.id))
    db.commit()
    return posts_json(db, [post], me)[0]


@router.get("/v1/bookmarks")
def bookmarks(
    me: Me,
    db: Db,
    cursor: int | None = Query(None, gt=0),
    limit: int = Query(20, ge=1, le=50),
):
    return page_posts(
        db,
        select(Post).where(
            Post.id.in_(select(Bookmark.post_id).where(Bookmark.user_id == me.id)),
            Post.parent_id.is_(None),
        ),
        me,
        cursor,
        limit,
    )


@router.put("/v1/posts/{post_id}/bookmark")
def bookmark(post_id: int, request: Request, me: Me, db: Db):
    quota(request, me)
    post = get_post(db, post_id, me)
    if post.parent_id:
        raise HTTPException(400, "Save the original post")
    if not db.get(Bookmark, (me.id, post.id)):
        db.add(Bookmark(user_id=me.id, post_id=post.id))
        commit_unique(db)
    return posts_json(db, [post], me)[0]


@router.delete("/v1/posts/{post_id}/bookmark")
def unbookmark(post_id: int, request: Request, me: Me, db: Db):
    quota(request, me)
    post = get_post(db, post_id, me)
    db.execute(
        delete(Bookmark).where(Bookmark.user_id == me.id, Bookmark.post_id == post.id)
    )
    db.commit()
    return posts_json(db, [post], me)[0]


@router.put("/v1/posts/{post_id}/report")
def report_post(post_id: int, data: ReportInput, request: Request, me: Me, db: Db):
    quota(request, me, "report", 5, 3600)
    post = get_post(db, post_id, me)
    if not db.get(Report, (me.id, post.id)):
        db.add(Report(reporter_id=me.id, post_id=post.id, reason=data.reason))
        commit_unique(db)
    return {"ok": True}
