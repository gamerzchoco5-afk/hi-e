"""Register, sign in, sign out and password change."""

from typing import Annotated
import secrets
from fastapi.security import HTTPAuthorizationCredentials
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from ..core.security import digest, limiter
from ..core.passwords import DUMMY_HASH, hash_password, passwords, verify_password
from ..core.constants import RESERVED
from ..models.identity import Session, User
from ..schemas.accounts import Credentials, PasswordChange, Register
from ..services.sessions import issue_session
from .deps import Db, Me, bearer, quota

router = APIRouter()


@router.post("/v1/auth/register", status_code=201)
def register(data: Register, request: Request, db: Db):
    quota(request, group="register", cap=5, window=3600)
    if data.username in RESERVED:
        raise HTTPException(409, "Choose another username")
    from wire_common.db import RecoveryCode, uid

    user = User(
        id=uid(),
        username=data.username,
        email=data.email,
        date_of_birth=data.date_of_birth,
        display_name=data.display_name,
        password_hash=hash_password(data.password),
    )
    codes = [secrets.token_hex(16).upper() for _ in range(8)]
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Account details are unavailable")
    db.add_all(
        [
            RecoveryCode(user_id=user.id, code_hash=digest(user.id + ":" + code))
            for code in codes
        ]
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409,
            "Account details are unavailable. Try signing in or choose another username.",
        )
    return {**issue_session(db, user), "recovery_codes": codes}


@router.post("/v1/auth/login")
def login(data: Credentials, request: Request, db: Db):
    quota(request, group="login", cap=20, window=900)
    limiter.check("login:account:" + data.username, 40, 900)
    user = db.scalar(
        select(User)
        .where(or_(User.username == data.username, User.email == data.username))
        .with_for_update()
    )
    valid = verify_password(user.password_hash if user else DUMMY_HASH, data.password)
    if not user or not valid or user.disabled:
        raise HTTPException(401, "Username or password is incorrect")
    if passwords.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(data.password)
    return issue_session(db, user)


@router.post("/v1/auth/logout")
def logout(
    me: Me,
    db: Db,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
):
    db.execute(
        delete(Session).where(Session.token_hash == digest(credentials.credentials))
    )
    db.commit()
    return {"ok": True}


@router.post("/v1/auth/logout-all")
def logout_all(me: Me, db: Db):
    db.execute(delete(Session).where(Session.user_id == me.id))
    db.commit()
    return {"ok": True}


@router.put("/v1/auth/password")
def change_password(data: PasswordChange, request: Request, me: Me, db: Db):
    quota(request, me, "password", 5, 900)
    db.refresh(me, with_for_update=True)
    if not verify_password(me.password_hash, data.current_password):
        raise HTTPException(400, "Current password is incorrect")
    me.password_hash = hash_password(data.new_password)
    db.execute(delete(Session).where(Session.user_id == me.id))
    return issue_session(db, me)
