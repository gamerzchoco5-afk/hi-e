"""Response builders shared by the account/social endpoints."""

from sqlalchemy import func, select
from ..models.identity import User
from ..models.social import Bookmark, Follow, Like, Post
from ..api.deps import hidden_ids


def profiles_json(db, users, me):
    if not users:
        return []
    ids = [user.id for user in users]
    followers = dict(
        db.execute(
            select(Follow.followed_id, func.count())
            .where(Follow.followed_id.in_(ids))
            .group_by(Follow.followed_id)
        ).all()
    )
    following_counts = dict(
        db.execute(
            select(Follow.follower_id, func.count())
            .where(Follow.follower_id.in_(ids))
            .group_by(Follow.follower_id)
        ).all()
    )
    posts = dict(
        db.execute(
            select(Post.author_id, func.count())
            .where(Post.author_id.in_(ids), Post.parent_id.is_(None))
            .group_by(Post.author_id)
        ).all()
    )
    following = set(
        db.scalars(
            select(Follow.followed_id).where(
                Follow.follower_id == me.id, Follow.followed_id.in_(ids)
            )
        )
    )
    return [
        {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "bio": user.bio,
            "pronouns": user.pronouns,
            "created_at": user.created_at,
            "avatar_version": user.avatar_version,
            "verification_status": "under_construction",
            "follower_count": followers.get(user.id, 0),
            "following_count": following_counts.get(user.id, 0),
            "post_count": posts.get(user.id, 0),
            "is_following": user.id in following,
            "is_me": user.id == me.id,
        }
        for user in users
    ]


def profile_json(db, user, me):
    return profiles_json(db, [user], me)[0]


def posts_json(db, posts, me):
    if not posts:
        return []
    ids = [p.id for p in posts]
    authors = {
        u.id: u
        for u in db.scalars(
            select(User).where(User.id.in_({p.author_id for p in posts}))
        )
    }
    likes = dict(
        db.execute(
            select(Like.post_id, func.count())
            .where(Like.post_id.in_(ids))
            .group_by(Like.post_id)
        ).all()
    )
    replies = dict(
        db.execute(
            select(Post.parent_id, func.count())
            .join(User, User.id == Post.author_id)
            .where(
                Post.parent_id.in_(ids),
                Post.author_id.not_in(hidden_ids(me)),
                User.disabled.is_(False),
            )
            .group_by(Post.parent_id)
        ).all()
    )
    liked = set(
        db.scalars(
            select(Like.post_id).where(Like.user_id == me.id, Like.post_id.in_(ids))
        )
    )
    saved = set(
        db.scalars(
            select(Bookmark.post_id).where(
                Bookmark.user_id == me.id, Bookmark.post_id.in_(ids)
            )
        )
    )
    following = set(
        db.scalars(
            select(Follow.followed_id).where(
                Follow.follower_id == me.id, Follow.followed_id.in_(authors)
            )
        )
    )
    return [
        {
            "id": p.id,
            "kind": p.kind,
            "title": p.title,
            "body": p.body,
            "parent_id": p.parent_id,
            "created_at": p.created_at,
            "like_count": likes.get(p.id, 0),
            "reply_count": replies.get(p.id, 0),
            "liked": p.id in liked,
            "bookmarked": p.id in saved,
            "author": {
                "id": p.author_id,
                "username": authors[p.author_id].username,
                "display_name": authors[p.author_id].display_name,
                "avatar_version": authors[p.author_id].avatar_version,
                "is_me": p.author_id == me.id,
                "is_following": p.author_id in following,
            },
        }
        for p in posts
    ]


def page_posts(db, statement, me, cursor, limit):
    statement = statement.join(User, User.id == Post.author_id).where(
        Post.author_id.not_in(hidden_ids(me)), User.disabled.is_(False)
    )
    if cursor:
        statement = statement.where(Post.id < cursor)
    posts = list(db.scalars(statement.order_by(Post.id.desc()).limit(limit + 1)))
    return {
        "items": posts_json(db, posts[:limit], me),
        "next_cursor": posts[limit - 1].id if len(posts) > limit else None,
    }
