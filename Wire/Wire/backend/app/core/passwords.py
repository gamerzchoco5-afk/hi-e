import secrets
import threading
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import HTTPException

# Argon2id; 64 MiB, three passes. Never log passwords or bearer tokens.
passwords = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
DUMMY_HASH = passwords.hash(secrets.token_urlsafe(32))
hash_slots = threading.BoundedSemaphore(2)


def hash_password(value):
    if not hash_slots.acquire(blocking=False):
        raise HTTPException(503, "Sign-in is busy. Try again in a moment.")
    try:
        return passwords.hash(value)
    finally:
        hash_slots.release()


def verify_password(stored, supplied):
    if not hash_slots.acquire(blocking=False):
        raise HTTPException(503, "Sign-in is busy. Try again in a moment.")
    try:
        return passwords.verify(stored, supplied)
    except (VerificationError, InvalidHashError):
        return False
    finally:
        hash_slots.release()
