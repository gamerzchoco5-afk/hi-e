import base64
import io
import uuid
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
from sqlalchemy import delete, select, update
from app.core.config import settings
from app.core.database import SessionLocal, now
from app.core.security import limiter
from app.models.identity import (
    EmailChallenge,
    RateBucket,
    RecoveryCode,
    Session,
    User,
)
from conftest import signup


def post(client, headers, body="Hello Wire", **extra):
    return client.post(
        "/v1/posts",
        headers=headers,
        json={"body": body, "client_id": str(uuid.uuid4()), **extra},
    )


def conversation(main, chat):
    a, av = signup(main, "alice")
    b, bv = signup(main, "bravo")
    c, cv = signup(main, "carol")
    r = chat.post("/v1/conversations", headers=a, json={"username": "bravo"})
    assert r.status_code == 201, r.text
    return a, b, c, r.json()["id"], av, bv, cv


def test_signup_email_username_uniqueness_and_privacy(main):
    headers, value = signup(main, verify=False)
    assert len(value["recovery_codes"]) == 8
    assert len(set(value["recovery_codes"])) == 8
    assert main.get("/v1/feed", headers=headers).status_code == 403
    assert main.get("/v1/me", headers=headers).json()["email"] == "alice@example.org"
    duplicate = {
        "username": "alice",
        "email": "other@example.org",
        "password": "my-secure-password-914",
        "display_name": "Other",
        "date_of_birth": "2000-01-01",
    }
    assert main.post("/v1/auth/register", json=duplicate).status_code == 409
    duplicate["username"] = "different"
    duplicate["email"] = "ALICE@example.org"
    assert main.post("/v1/auth/register", json=duplicate).status_code == 409
    assert main.get("/v1/auth/username?username=alice").json() == {"available": False}
    assert main.get("/v1/auth/username?username=available_name").json() == {
        "available": True
    }
    assert main.get("/v1/auth/username?username=admin").json() == {"available": False}
    assert (
        main.post(
            "/v1/auth/login",
            json={
                "username": "ALICE@example.org",
                "password": "my-secure-password-914",
            },
        ).status_code
        == 200
    )


def test_recovery_code_single_use_revokes_sessions(main):
    headers, value = signup(main)
    code = value["recovery_codes"][0]
    with SessionLocal() as db:
        assert db.scalar(select(RecoveryCode.code_hash)) != code
    payload = {
        "username": "alice",
        "code": code,
        "new_password": "new-strong-password-992",
    }
    response = main.post("/v1/auth/recover", json=payload)
    assert response.status_code == 200, response.text
    assert main.get("/v1/me", headers=headers).status_code == 401
    assert main.post("/v1/auth/recover", json=payload).status_code == 400
    assert (
        main.post(
            "/v1/auth/login",
            json={"username": "alice", "password": "my-secure-password-914"},
        ).status_code
        == 401
    )
    assert (
        main.post(
            "/v1/auth/login",
            json={"username": "alice", "password": payload["new_password"]},
        ).status_code
        == 200
    )


def test_concurrent_recovery_code_consumption(main):
    headers, value = signup(main)
    payload = {
        "username": "alice",
        "code": value["recovery_codes"][0],
        "new_password": "new-strong-password-993",
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(
            pool.map(
                lambda _: main.post("/v1/auth/recover", json=payload).status_code,
                range(2),
            )
        )
    assert sorted(statuses) == [200, 400]


def test_code_replacement_requires_password(main):
    headers, value = signup(main)
    assert (
        main.post(
            "/v1/auth/recovery-codes",
            headers=headers,
            json={"current_password": "wrong"},
        ).status_code
        == 400
    )
    r = main.post(
        "/v1/auth/recovery-codes",
        headers=headers,
        json={"current_password": "my-secure-password-914"},
    )
    assert r.status_code == 200, r.text
    assert (
        main.post(
            "/v1/auth/recover",
            json={
                "username": "alice",
                "code": value["recovery_codes"][0],
                "new_password": "a-new-password-8912",
            },
        ).status_code
        == 400
    )


def test_email_code_expiry_and_one_time_use(main, monkeypatch):
    headers, value = signup(main, verify=False)
    codes = []
    monkeypatch.setattr(
        "app.api.account.send_verification", lambda email, code: codes.append(code)
    )
    assert main.post("/v1/auth/email/send", headers=headers).status_code == 200
    assert (
        main.post(
            "/v1/auth/email/verify",
            headers=headers,
            json={"code": "99999999" if codes[0] != "99999999" else "00000000"},
        ).status_code
        == 400
    )
    assert (
        main.post(
            "/v1/auth/email/verify", headers=headers, json={"code": codes[0]}
        ).status_code
        == 200
    )
    assert (
        main.post(
            "/v1/auth/email/verify", headers=headers, json={"code": codes[0]}
        ).status_code
        == 400
    )
    assert main.get("/v1/feed", headers=headers).status_code == 200
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "alice"))
        user.email_verified = False
        db.commit()
    assert main.post("/v1/auth/email/send", headers=headers).status_code == 200
    with SessionLocal() as db:
        db.execute(update(EmailChallenge).values(expires_at=now() - 1))
        db.commit()
    assert (
        main.post(
            "/v1/auth/email/verify", headers=headers, json={"code": codes[-1]}
        ).status_code
        == 400
    )


def test_sessions_revoke_only_owner(main):
    a, av = signup(main)
    b, bv = signup(main, "bravo")
    sid = main.get("/v1/auth/sessions", headers=a).json()["items"][0]["id"]
    assert main.delete("/v1/auth/sessions/" + sid, headers=b).status_code == 200
    assert main.get("/v1/me", headers=a).status_code == 200
    assert main.delete("/v1/auth/sessions/" + sid, headers=a).status_code == 200
    assert main.get("/v1/me", headers=a).status_code == 401


def test_server_enforces_timeout_and_disabled_in_both_services(main, chat):
    a, av = signup(main)
    with SessionLocal() as db:
        db.execute(
            update(User)
            .where(User.username == "alice")
            .values(timed_out_until=now() + 600)
        )
        db.commit()
    for client, path in [(main, "/v1/feed"), (chat, "/v1/conversations")]:
        r = client.get(path, headers=a)
        assert r.status_code == 423, r.text
        assert int(r.headers["retry-after"]) > 0
    with SessionLocal() as db:
        db.execute(
            update(User)
            .where(User.username == "alice")
            .values(timed_out_until=0, disabled=True)
        )
        db.commit()
    assert main.get("/v1/me", headers=a).status_code == 401
    assert chat.get("/v1/conversations", headers=a).status_code == 401


def test_posts_idempotency_ownership_and_server_counts(main):
    a, av = signup(main)
    b, bv = signup(main, "bravo")
    body = {"body": "Hello", "client_id": str(uuid.uuid4())}
    first = main.post("/v1/posts", headers=a, json=body)
    second = main.post("/v1/posts", headers=a, json=body)
    assert first.status_code == 201, first.text
    assert first.json()["id"] == second.json()["id"]
    assert (
        main.post("/v1/posts", headers=a, json={**body, "body": "Changed"}).status_code
        == 409
    )
    identity = str(first.json()["id"])
    assert main.delete("/v1/posts/" + identity, headers=b).status_code == 403
    for _ in range(2):
        assert main.put("/v1/posts/" + identity + "/like", headers=b).status_code == 200
    assert main.get("/v1/posts/" + identity, headers=a).json()["like_count"] == 1
    assert post(main, a, like_count=1000).status_code == 422
    assert post(main, a, "x" * 501).status_code == 422
    assert post(main, a, "x" * 10001, kind="article", title="Title").status_code == 422


def test_block_hides_posts_profiles_and_chat(main, chat):
    a, b, c, identity, *_ = conversation(main, chat)
    assert post(main, a).status_code == 201
    assert main.put("/v1/users/alice/block", headers=b).status_code == 200
    assert main.get("/v1/users/alice", headers=b).status_code == 404
    assert main.get("/v1/feed", headers=b).json()["items"] == []
    assert (
        chat.get("/v1/conversations/" + identity + "/messages", headers=b).status_code
        == 404
    )
    assert (
        chat.post(
            "/v1/conversations", headers=a, json={"username": "bravo"}
        ).status_code
        == 404
    )


def test_chat_membership_pending_requests_and_idempotency(main, chat):
    a, b, c, identity, *_ = conversation(main, chat)
    path = "/v1/conversations/" + identity
    assert chat.get(path + "/messages", headers=c).status_code == 404
    body = {"body": "Hello", "client_id": str(uuid.uuid4())}
    first = chat.post(path + "/messages", headers=a, json=body)
    assert first.status_code == 201, first.text
    assert (
        chat.post(
            path + "/messages", headers=a, json={**body, "body": "Changed"}
        ).status_code
        == 409
    )
    assert (
        chat.post(path + "/messages", headers=a, json=body).json()["id"]
        == first.json()["id"]
    )
    assert (
        chat.post(
            path + "/messages",
            headers=a,
            json={"body": "Again", "client_id": str(uuid.uuid4())},
        ).status_code
        == 403
    )
    assert chat.put(path + "/accept", headers=a).status_code == 403
    assert chat.put(path + "/accept", headers=b).status_code == 200
    assert (
        chat.post(
            path + "/messages",
            headers=b,
            json={"body": "Hey", "client_id": str(uuid.uuid4())},
        ).status_code
        == 201
    )
    assert (
        chat.put(path + "/read", headers=b, json={"message_id": 999999}).status_code
        == 422
    )
    message = str(first.json()["id"])
    assert chat.delete("/v1/messages/" + message, headers=b).status_code == 404
    assert chat.delete("/v1/messages/" + message, headers=a).status_code == 200
    assert chat.get(path + "/messages", headers=b).json()["items"][0]["deleted"]
    assert chat.get("/v1/conversations", headers=c).json()["items"] == []


def test_privacy_blocks_new_chat_requests(main, chat):
    a, av = signup(main)
    b, bv = signup(main, "bravo")
    assert (
        main.put(
            "/v1/settings",
            headers=b,
            json={"message_requests": False, "show_activity": False},
        ).status_code
        == 200
    )
    assert (
        chat.post(
            "/v1/conversations", headers=a, json={"username": "bravo"}
        ).status_code
        == 403
    )
    assert main.put("/v1/users/alice/follow", headers=b).status_code == 200
    assert (
        chat.post(
            "/v1/conversations", headers=a, json={"username": "bravo"}
        ).status_code
        == 201
    )


def test_profile_photo_validation_and_no_metadata(main):
    a, av = signup(main)
    b, bv = signup(main, "bravo")
    image = Image.new("RGB", (600, 600), "red")
    out = io.BytesIO()
    image.save(out, "PNG")
    assert (
        main.put(
            "/v1/me/avatar",
            headers=a,
            json={"content_base64": base64.b64encode(out.getvalue()).decode()},
        ).status_code
        == 200
    )
    response = main.get("/v1/users/alice/avatar", headers=b)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/webp"
    decoded = Image.open(io.BytesIO(response.content))
    assert decoded.size == (512, 512)
    assert (
        main.put(
            "/v1/me/avatar",
            headers=a,
            json={
                "content_base64": base64.b64encode(b'<svg onload="alert(1)">').decode()
            },
        ).status_code
        == 422
    )
    assert main.put("/v1/users/alice/block", headers=b).status_code == 200
    assert main.get("/v1/users/alice/avatar", headers=b).status_code == 404


def test_password_change_and_delete_cascade(main, chat):
    a, b, c, identity, *_ = conversation(main, chat)
    password = "new-password-123941"
    r = main.put(
        "/v1/auth/password",
        headers=a,
        json={"current_password": "my-secure-password-914", "new_password": password},
    )
    assert r.status_code == 200, r.text
    assert main.get("/v1/me", headers=a).status_code == 401
    a = {"Authorization": "Bearer " + r.json()["token"]}
    assert (
        main.request(
            "DELETE", "/v1/me", headers=a, json={"password": password}
        ).status_code
        == 200
    )
    assert (
        chat.get("/v1/conversations/" + identity + "/messages", headers=b).status_code
        == 404
    )
    assert chat.get("/v1/conversations", headers=b).json()["items"] == []


def test_validation_body_bounds_no_secret_echo_and_blue_tick(main):
    a, av = signup(main)
    assert (
        main.get("/v1/settings", headers=a).json()["verification_status"]
        == "under_construction"
    )
    assert (
        main.put(
            "/v1/me",
            headers=a,
            json={"username": "bad@email.com", "display_name": "User"},
        ).status_code
        == 422
    )
    r = main.post(
        "/v1/auth/register", json={"username": "x", "password": "secret-sentinel"}
    )
    assert r.status_code == 422
    assert "secret-sentinel" not in r.text
    assert (
        main.post(
            "/v1/posts", headers={**a, "Content-Type": "text/plain"}, content="test"
        ).status_code
        == 415
    )
    assert (
        main.post("/v1/posts", headers=a, json={"body": "x" * 70000}).status_code == 413
    )
    assert (
        main.get(
            "/v1/feed", headers={"Authorization": "Bearer " + ("x" * 101)}
        ).status_code
        == 401
    )


def test_distributed_database_rate_limiter_is_atomic(main):
    cfg = settings()
    cfg.rate_limits_enabled = True
    try:
        with SessionLocal() as db:
            db.execute(delete(RateBucket))
            db.commit()

        def check(_):
            try:
                limiter.check("test-shared-limit", 5, 3600)
                return True
            except Exception as error:
                assert error.status_code == 429
                return False

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(check, range(12)))
        assert sum(results) == 5
    finally:
        cfg.rate_limits_enabled = False


def test_expired_sessions_denied_by_both_services(main, chat):
    headers, value = signup(main)
    with SessionLocal() as db:
        db.execute(update(Session).values(expires_at=now() - 1))
        db.commit()
    assert main.get("/v1/me", headers=headers).status_code == 401
    assert chat.get("/v1/conversations", headers=headers).status_code == 401


def test_spoofed_forwarded_headers_do_not_bypass_rate_limits(main):
    cfg = settings()
    cfg.rate_limits_enabled = True
    try:
        for attempt in range(30):
            response = main.get(
                "/v1/auth/username?username=available_name",
                headers={"X-Forwarded-For": "203.0.113." + str(attempt)},
            )
            assert response.status_code == 200, response.text
        response = main.get(
            "/v1/auth/username?username=available_name",
            headers={"X-Forwarded-For": "198.51.100.255"},
        )
        assert response.status_code == 429
        assert 0 < int(response.headers["retry-after"]) <= 60
    finally:
        cfg.rate_limits_enabled = False


def test_app_role_and_mass_assignment_boundaries(main, chat):
    a, av = signup(main)
    b, bv = signup(main, "bravo")
    assert "email" not in main.get("/v1/users/alice", headers=b).json()
    assert "date_of_birth" not in main.get("/v1/users/alice", headers=b).json()
    assert (
        main.put(
            "/v1/me",
            headers=a,
            json={
                "username": "alice",
                "display_name": "A",
                "disabled": False,
                "verified": True,
            },
        ).status_code
        == 422
    )
    assert main.get("/v1/conversations", headers=a).status_code == 404
    assert (
        chat.post(
            "/v1/auth/login",
            json={"username": "alice", "password": "my-secure-password-914"},
        ).status_code
        == 404
    )
    assert (
        main.get("/v1/me", headers={**a, "Host": "attacker.example"}).status_code == 400
    )


def test_weak_password_and_age_validation(main):
    payload = {
        "username": "sample_user",
        "display_name": "Sample",
        "email": "sample@example.org",
        "date_of_birth": "2000-01-01",
        "password": "aaaaaaaaaaaa",
    }
    assert main.post("/v1/auth/register", json=payload).status_code == 422
    payload["password"] = "abcdabcdabcd"
    assert main.post("/v1/auth/register", json=payload).status_code == 422
    payload["password"] = "my-secure-password-914"
    payload["date_of_birth"] = "2020-01-01"
    assert main.post("/v1/auth/register", json=payload).status_code == 422


def test_pending_and_read_receipt_privacy(main, chat):
    a, b, c, identity, *_ = conversation(main, chat)
    path = "/v1/conversations/" + identity
    assert chat.put(path + "/accept", headers=b).status_code == 200
    sent = chat.post(
        path + "/messages",
        headers=a,
        json={"body": "Read test", "client_id": str(uuid.uuid4())},
    ).json()
    assert (
        chat.put(path + "/read", headers=b, json={"message_id": sent["id"]}).status_code
        == 200
    )
    assert chat.get(path + "/messages", headers=a).json()["peer_read"] == sent["id"]
    assert (
        main.put(
            "/v1/settings",
            headers=b,
            json={"message_requests": True, "show_activity": False},
        ).status_code
        == 200
    )
    assert chat.get(path + "/messages", headers=a).json()["peer_read"] == 0
    assert (
        chat.put(path + "/report", headers=c, json={"reason": "not mine"}).status_code
        == 404
    )


def test_concurrent_authenticated_reads_do_not_starve_rate_pool(main):
    headers, value = signup(main)
    cfg = settings()
    cfg.rate_limits_enabled = True
    try:
        with ThreadPoolExecutor(max_workers=12) as pool:
            responses = list(
                pool.map(lambda _: main.get("/v1/me", headers=headers), range(12))
            )
        assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    finally:
        cfg.rate_limits_enabled = False
