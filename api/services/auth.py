"""
Sign-in, password hashing and the session token.

The browser used to sign in by downloading the user's row - password hash
included - and comparing hashes itself, with row-level security off. Anyone
with the public anon key could read every account. Now:

  - Passwords are checked here, server side, and stored as bcrypt. Accounts
    still on the old unsalted SHA-256 hash are upgraded to bcrypt the first
    time they sign in, so nobody has to reset a password.
  - A successful sign-in returns one signed session token (HS256 JWT). The web
    app sends it to this API (Authorization: Bearer ...) and to Supabase, which
    verifies the same signature and applies row-level security from its claims
    (see supabase/migrations/07_security_rls.sql).

The token is signed with SUPABASE_JWT_SECRET (Supabase dashboard > Project
Settings > JWT Keys > Legacy JWT secret), which is what lets Supabase accept
it. Without that secret the API falls back to AUTH_SECRET: sign-in and API
protection still work, but the token cannot be sent to the database, so
database access stays on the anon key until the secret is configured.

DEMO_MODE=true additionally lets the built-in demo accounts (ids like
"usr-command-staff-1", no database row) get a token, for presentations. Leave
it off in production.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from dataclasses import dataclass

import bcrypt
import jwt

logger = logging.getLogger("rescueeye.auth")

ROLES = ("SYSTEM_ADMIN", "AGENCY_ADMIN", "COMMAND_STAFF", "FIELD_RESPONDER")
TOKEN_TTL_S = int(os.getenv("AUTH_TOKEN_TTL_HOURS", "12")) * 3600
MIN_PASSWORD_LENGTH = 8

_supabase_secret = os.getenv("SUPABASE_JWT_SECRET", "").strip()
_fallback_secret = os.getenv("AUTH_SECRET", "").strip()
if not _supabase_secret and not _fallback_secret:
    # Tokens from a random per-process secret stop working when the API
    # restarts (everyone signs in again) - acceptable for development, and
    # loud so it is not mistaken for a production setup.
    _fallback_secret = secrets.token_urlsafe(48)
    logger.warning("[auth] neither SUPABASE_JWT_SECRET nor AUTH_SECRET is set - sessions end when the API restarts")
_secret = _supabase_secret or _fallback_secret

# The token is a valid Supabase session only when signed with its secret.
DATABASE_TOKENS = bool(_supabase_secret)


def demo_mode() -> bool:
    return os.getenv("DEMO_MODE", "false").strip().lower() == "true"


# ── Passwords ────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def _is_legacy_hash(stored: str) -> bool:
    return len(stored) == 64 and all(c in "0123456789abcdef" for c in stored.lower())


def verify_password(password: str, stored: str | None) -> tuple[bool, bool]:
    """(matches, needs_rehash). needs_rehash is True for a correct password still on the legacy SHA-256 hash."""
    if not stored:
        return False, False
    if _is_legacy_hash(stored):
        legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
        ok = hmac.compare_digest(legacy, stored.lower())
        return ok, ok
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored.encode("ascii")), False
    except ValueError:
        return False, False


def password_problem(password: str) -> str | None:
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    return None


# ── Session tokens ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Principal:
    """Who is making a request, as the verified token states it."""
    user_id: str
    role: str
    agency_id: str | None
    demo: bool = False

    @property
    def db_id(self) -> int | None:
        """The numeric database id, or None for a demo account."""
        return int(self.user_id) if self.user_id.isdigit() else None


def issue_token(user_id: str, role: str, agency_id: str | None, *, demo: bool = False) -> str:
    now = int(time.time())
    claims = {
        "sub": str(user_id),
        # Supabase/PostgREST switches to this Postgres role for the request.
        "role": "authenticated",
        "aud": "authenticated",
        "iat": now,
        "exp": now + TOKEN_TTL_S,
        "app_role": role,
        "agency_id": int(agency_id) if agency_id and str(agency_id).isdigit() else None,
        "demo_agency_id": None if agency_id and str(agency_id).isdigit() else agency_id,
        "demo": demo,
    }
    return jwt.encode(claims, _secret, algorithm="HS256")


class InvalidToken(Exception):
    pass


def read_token(token: str) -> Principal:
    try:
        claims = jwt.decode(token, _secret, algorithms=["HS256"], audience="authenticated")
    except jwt.ExpiredSignatureError as exc:
        raise InvalidToken("Your session has expired. Sign in again.") from exc
    except jwt.PyJWTError as exc:
        raise InvalidToken("Invalid session. Sign in again.") from exc
    role = claims.get("app_role")
    if role not in ROLES or not claims.get("sub"):
        raise InvalidToken("Invalid session. Sign in again.")
    demo = bool(claims.get("demo"))
    if demo and not demo_mode():
        raise InvalidToken("Demo accounts are disabled on this server.")
    agency = claims.get("agency_id")
    agency_id = str(agency) if agency is not None else claims.get("demo_agency_id")
    return Principal(user_id=str(claims["sub"]), role=role, agency_id=agency_id, demo=demo)
