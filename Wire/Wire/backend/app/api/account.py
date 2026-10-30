"""Recovery codes, email verification, settings, avatars and sessions."""

import base64
import hashlib
import hmac
import io
import secrets
import smtplib
import ssl
import threading
from email.message import EmailMessage
from typing import Annotated
from fastapi.security import HTTPAuthorizationCredentials
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import Field
from sqlalchemy import delete, or_, select
from PIL import Image, ImageOps, UnidentifiedImageError
from ..core.config import settings
from ..core.database import now
from ..models.identity import Avatar, EmailChallenge, RecoveryCode, Session, User
from ..core.security import digest, limiter
from ..core.passwords import hash_password, verify_password
from ..schemas.accounts import EmailCodeInput, Input, RecoveryInput, SettingsEdit


class PasswordProof(Input):
    current_password: str = Field(min_length=1, max_length=128)


class AvatarInput(Input):
    content_base64: str = Field(max_length=1400000)


def email_digest(user_id, code):
    return hmac.new(
        settings().email_code_pepper.encode(),
        (user_id + ":" + code).encode(),
        hashlib.sha256,
    ).hexdigest()


def send_verification(address, code):
    cfg = settings()
    if not cfg.smtp_host or not cfg.smtp_from or len(cfg.email_code_pepper) < 32:
        raise HTTPException(503, "Email delivery is not configured yet")
    message = EmailMessage()
    message["Subject"] = "Verify your Wire email"
    message["From"] = cfg.smtp_from
    message["To"] = address
    message.set_content(
        "Your Wire verification code is "
        + code
        + ". It expires in 10 minutes. Do not share it."
    )
    try:
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=8) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if cfg.smtp_user:
                smtp.login(cfg.smtp_user, cfg.smtp_password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException):
        raise HTTPException(503, "Email delivery is temporarily unavailable")


image_slots = threading.BoundedSemaphore(2)


def normalize_avatar(encoded):
    if not image_slots.acquire(blocking=False):
        raise HTTPException(503, "Photo uploads are busy. Try again shortly.")
    try:
        return _normalize_avatar(encoded)
    finally:
        image_slots.release()


def _normalize_avatar(encoded):
    try:
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > 1048576:
            raise ValueError()
        with Image.open(io.BytesIO(raw), formats=("JPEG", "PNG", "WEBP")) as image:
            if (
                image.format not in ("JPEG", "PNG", "WEBP")
                or image.width * image.height > 8000000
                or getattr(image, "n_frames", 1) != 1
            ):
                raise ValueError()
            image.load()
            image = ImageOps.exif_transpose(image).convert("RGB")
            image = ImageOps.fit(image, (512, 512), method=Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="WEBP", quality=80, method=4)
            content = output.getvalue()
            if len(content) > 160000:
                raise ValueError()
            return content
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
        raise HTTPException(
            422, "Choose a valid non-animated JPEG, PNG or WebP photo under 1 MB"
        )

from ..core.constants import RESERVED
from ..services.sessions import issue_session
from .deps import Db, Me, bearer, get_profile, quota

router = APIRouter()


@router.get("/v1/auth/username")
def username_available(
    request: Request, db: Db, username: str = Query(pattern=r"^[a-z0-9_]{3,24}$")
):
    
    quota(request, group="username", cap=30, window=60)
    return {
        "available": username not in RESERVED
        and not db.scalar(select(User.id).where(User.username == username))
    }


@router.post("/v1/auth/recover")
def recover(data: RecoveryInput, request: Request, db: Db):
    quota(request, group="recover", cap=5, window=900)
    limiter.check("recover:account:" + data.username, 5, 900)
    user = db.scalar(
        select(User)
        .where(or_(User.username == data.username, User.email == data.username))
        .with_for_update()
    )
    code = data.code.replace("-", "").replace(" ", "").upper()
    hashed = digest((user.id if user else "missing") + ":" + code)
    password_hash = hash_password(data.new_password)
    if not user or user.disabled:
        raise HTTPException(400, "Account or recovery code is incorrect")
    consumed = db.execute(
        delete(RecoveryCode)
        .where(RecoveryCode.user_id == user.id, RecoveryCode.code_hash == hashed)
        .returning(RecoveryCode.user_id)
    ).scalar_one_or_none()
    if not consumed:
        raise HTTPException(400, "Account or recovery code is incorrect")
    user.password_hash = password_hash
    db.execute(delete(Session).where(Session.user_id == user.id))
    return issue_session(db, user)


@router.post("/v1/auth/recovery-codes")
def new_recovery_codes(data: PasswordProof, request: Request, me: Me, db: Db):
    quota(request, me, "security", 3, 900)
    db.refresh(me, with_for_update=True)
    if not verify_password(me.password_hash, data.current_password):
        raise HTTPException(400, "Current password is incorrect")
    codes = [secrets.token_hex(16).upper() for _ in range(8)]
    db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == me.id))
    db.add_all(
        [
            RecoveryCode(user_id=me.id, code_hash=digest(me.id + ":" + code))
            for code in codes
        ]
    )
    db.commit()
    return {"recovery_codes": codes}


@router.post("/v1/auth/email/send")
def email_send(request: Request, me: Me, db: Db):
    quota(request, me, "email-send", 3, 3600)
    if me.email_verified:
        return {"ok": True}
    code = str(secrets.randbelow(100000000)).zfill(8)
    challenge = db.get(EmailChallenge, me.id)
    if not challenge:
        challenge = EmailChallenge(user_id=me.id)
        db.add(challenge)
    challenge.code_hash = email_digest(me.id, code)
    challenge.expires_at = now() + 600
    db.commit()
    send_verification(me.email, code)
    return {"ok": True}


@router.post("/v1/auth/email/verify")
def email_verify(data: EmailCodeInput, request: Request, me: Me, db: Db):
    quota(request, me, "email-verify", 5, 900)
    matched = db.execute(
        delete(EmailChallenge)
        .where(
            EmailChallenge.user_id == me.id,
            EmailChallenge.expires_at > now(),
            EmailChallenge.code_hash == email_digest(me.id, data.code),
        )
        .returning(EmailChallenge.user_id)
    ).scalar_one_or_none()
    if not matched:
        raise HTTPException(400, "Verification code is incorrect or expired")
    me.email_verified = True
    db.commit()
    return {"ok": True}


@router.get("/v1/settings")
def get_settings(me: Me):
    return {
        "message_requests": me.message_requests,
        "show_activity": me.show_activity,
        "verification_status": "under_construction",
        "email_verified": me.email_verified,
    }


@router.put("/v1/settings")
def update_settings(data: SettingsEdit, request: Request, me: Me, db: Db):
    quota(request, me, "settings", 10, 60)
    me.message_requests = data.message_requests
    me.show_activity = data.show_activity
    db.commit()
    return get_settings(me)


@router.put("/v1/me/avatar")
def set_avatar(data: AvatarInput, request: Request, me: Me, db: Db):
    quota(request, me, "avatar", 5, 3600)
    content = normalize_avatar(data.content_base64)
    avatar = db.get(Avatar, me.id)
    if avatar:
        avatar.content = content
    else:
        db.add(Avatar(user_id=me.id, content=content))
    me.avatar_version += 1
    db.commit()
    return {"avatar_version": me.avatar_version}


@router.delete("/v1/me/avatar")
def remove_avatar(request: Request, me: Me, db: Db):
    quota(request, me, "avatar", 5, 3600)
    db.execute(delete(Avatar).where(Avatar.user_id == me.id))
    me.avatar_version += 1
    db.commit()
    return {"ok": True}


@router.get("/v1/users/{username}/avatar")
def get_avatar(username: str, me: Me, db: Db):
    
    user = get_profile(db, username, me)
    avatar = db.get(Avatar, user.id)
    if not avatar:
        raise HTTPException(404, "No profile photo")
    return Response(
        avatar.content,
        media_type="image/webp",
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/v1/auth/sessions")
def sessions(
    me: Me,
    db: Db,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
):
    current = digest(credentials.credentials)
    rows = db.scalars(
        select(Session)
        .where(Session.user_id == me.id, Session.expires_at > now())
        .order_by(Session.created_at.desc())
        .limit(10)
    )
    return {
        "items": [
            {
                "id": s.token_hash,
                "created_at": s.created_at,
                "expires_at": s.expires_at,
                "is_current": s.token_hash == current,
            }
            for s in rows
        ]
    }


@router.delete("/v1/auth/sessions/{identity}")
def revoke_session(identity: str, request: Request, me: Me, db: Db):
    quota(request, me, "security", 10, 900)
    db.execute(
        delete(Session).where(
            Session.token_hash == identity, Session.user_id == me.id
        )
    )
    db.commit()
    return {"ok": True}
