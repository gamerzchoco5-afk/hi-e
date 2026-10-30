"""The signed-in user: read, edit and delete."""

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from ..core.passwords import verify_password
from ..core.constants import RESERVED
from ..schemas.accounts import DeleteAccount, ProfileEdit
from ..services.serializers import profile_json
from .deps import Db, Me, quota

router = APIRouter()


@router.get("/v1/me")
def whoami(me: Me, db: Db):
    return {
        **profile_json(db, me, me),
        "email": me.email,
        "email_verified": me.email_verified,
        "message_requests": me.message_requests,
        "show_activity": me.show_activity,
    }


@router.put("/v1/me")
def edit_profile(data: ProfileEdit, request: Request, me: Me, db: Db):
    quota(request, me, "profile", 10, 60)
    if data.username in RESERVED:
        raise HTTPException(409, "Choose another username")
    for key, value in data.model_dump().items():
        setattr(me, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Choose another username")
    return profile_json(db, me, me)


@router.delete("/v1/me")
def delete_account(data: DeleteAccount, request: Request, me: Me, db: Db):
    quota(request, me, "password", 5, 900)
    db.refresh(me, with_for_update=True)
    if not verify_password(me.password_hash, data.password):
        raise HTTPException(400, "Password is incorrect")
    db.delete(me)
    db.commit()
    return {"ok": True}
