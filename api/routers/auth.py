"""
Sign-in and every write that sets a password (services/auth.py explains why
these moved off the browser).

POST /auth/login        email + password -> session token and the user's session
POST /auth/demo         a built-in demo account -> token (DEMO_MODE only)
POST /auth/register     organization sign-up: inactive Agency Admin + pending agency
POST /auth/users        Agency Admin adds Command Staff / Field Responder to their agency
POST /auth/password     change your own password
GET  /auth/me           the session the token describes
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from routers.deps import current_user, require_roles
from services import auth, supabase_db

logger = logging.getLogger("rescueeye.auth")
router = APIRouter()

INVALID_LOGIN = "Invalid email or password."


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _run(coro):
    try:
        return await coro
    except supabase_db.DatabaseNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc
    except supabase_db.DatabaseError as exc:
        logger.error(f"[auth] database error: {exc}")
        raise HTTPException(502, "The database could not complete this request. Try again.") from exc


async def _user_by_email(email: str) -> dict | None:
    # Case-insensitive exact match: login has always ignored email case.
    rows = await supabase_db.select_raw("user", {
        "select": "*",
        "email": f"ilike.{supabase_db.postgrest_escape_like(email.strip())}",
        "limit": "2",
    })
    return rows[0] if rows else None


def _session_payload(user: dict, agency_name: str | None, token: str) -> dict:
    name = " ".join(p for p in (user.get("firstName"), user.get("lastName")) if p).strip()
    return {
        "token": token,
        # Only a token signed with Supabase's secret may be sent to the database.
        "databaseToken": token if auth.DATABASE_TOKENS else None,
        "session": {
            "id": str(user["id"]),
            "name": name or user.get("email", ""),
            "email": user["email"],
            "role": user["role"],
            "agencyId": str(user["agencyId"]) if user.get("agencyId") is not None else None,
            "agencyName": agency_name,
        },
    }


# ── Sign-in ──────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


@router.post("/login")
async def login(body: LoginRequest) -> dict:
    user = await _run(_user_by_email(body.email))
    ok, needs_rehash = auth.verify_password(body.password, user.get("passwordHash") if user else None)
    if not user or not ok:
        raise HTTPException(401, INVALID_LOGIN)
    if not user.get("active"):
        raise HTTPException(403, "This account has been deactivated.")
    if user.get("role") not in auth.ROLES:
        raise HTTPException(403, "This account has no valid role. Contact your administrator.")

    if needs_rehash:
        # Upgrade from the old unsalted SHA-256 hash, now that we hold the password.
        await _run(supabase_db.update("user", user["id"], {"passwordHash": auth.hash_password(body.password)}))
        logger.info(f"[auth] user {user['id']} password hash upgraded to bcrypt")

    agency_name = None
    if user.get("agencyId") is not None:
        agencies = await _run(supabase_db.select("agency", id=user["agencyId"]))
        agency_name = agencies[0].get("name") if agencies else None

    token = auth.issue_token(str(user["id"]), user["role"], str(user["agencyId"]) if user.get("agencyId") else None)
    return _session_payload(user, agency_name, token)


class DemoLoginRequest(BaseModel):
    id: str = Field(pattern=r"^usr-[a-z0-9-]+$")
    role: str
    agencyId: str | None = None


@router.post("/demo")
async def demo_login(body: DemoLoginRequest) -> dict:
    """The built-in demo accounts live in the web app (src/data/mockUsers.ts), so their password is checked there."""
    if not auth.demo_mode():
        raise HTTPException(403, "Demo accounts are disabled on this server.")
    if body.role not in auth.ROLES:
        raise HTTPException(422, "Unknown role.")
    return {"token": auth.issue_token(body.id, body.role, body.agencyId, demo=True), "databaseToken": None}


@router.get("/me")
async def me(user: auth.Principal = Depends(current_user)) -> dict:
    return {"id": user.user_id, "role": user.role, "agencyId": user.agency_id, "demo": user.demo}


# ── Organization sign-up ─────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    agencyName: str = Field(min_length=2, max_length=200)
    agencyType: str = Field(min_length=1, max_length=100)
    agencyAddress: str = Field(min_length=1, max_length=500)
    agencyAddressRegionCode: str | None = None
    agencyAddressProvinceCode: str | None = None
    agencyAddressCityCode: str | None = None
    agencyAddressBarangayCode: str | None = None
    agencyPhone: str = Field(min_length=1, max_length=40)
    agencyEmail: str = Field(min_length=3, max_length=254)
    agencyWebsite: str | None = Field(default=None, max_length=300)
    adminFirstName: str = Field(min_length=1, max_length=100)
    adminMiddleName: str = Field(min_length=1, max_length=100)
    adminLastName: str = Field(min_length=1, max_length=100)
    adminPosition: str = Field(min_length=1, max_length=100)
    adminEmail: str = Field(min_length=3, max_length=254)
    adminPhone: str = Field(min_length=1, max_length=40)
    adminPassword: str = Field(min_length=1, max_length=200)


async def _insert_tolerating_missing_columns(table: str, row: dict, optional: list[str]) -> dict:
    """
    Inserts `row`, dropping an `optional` column the database rejects as unknown
    (PGRST204) - registration keeps working on a database where migrations
    02/04 have not been run yet, as it did when the browser did this.
    """
    current = dict(row)
    while True:
        try:
            return (await supabase_db.insert(table, current))[0]
        except supabase_db.DatabaseError as exc:
            missing = next((c for c in optional if c in current and "PGRST204" in str(exc) and c in str(exc)), None)
            if not missing:
                raise
            logger.warning(f"[auth] {table}.{missing} column missing - run its migration; saving without it")
            current.pop(missing)


@router.post("/register", status_code=201)
async def register(body: RegisterRequest) -> dict:
    problem = auth.password_problem(body.adminPassword)
    if problem:
        raise HTTPException(422, problem)
    if await _run(_user_by_email(body.adminEmail)):
        raise HTTPException(409, "An account with this email address already exists. Sign in instead, or use a different email.")

    user_id: int | None = None
    agency_id: int | None = None
    try:
        user = await _insert_tolerating_missing_columns("user", {
            "email": body.adminEmail.strip(),
            "passwordHash": auth.hash_password(body.adminPassword),
            "firstName": body.adminFirstName.strip(),
            "middleName": body.adminMiddleName.strip(),
            "lastName": body.adminLastName.strip(),
            "position": body.adminPosition.strip(),
            "phone": body.adminPhone.strip(),
            "role": "AGENCY_ADMIN",
            "agencyId": None,
            "active": False,  # until a System Admin approves the agency
            "createdAt": _now(),
        }, ["middleName"])
        user_id = user["id"]
        agency = await _insert_tolerating_missing_columns("agency", {
            "name": body.agencyName.strip(),
            "agencyType": body.agencyType,
            "address": body.agencyAddress.strip(),
            "addressRegionCode": body.agencyAddressRegionCode or None,
            "addressProvinceCode": body.agencyAddressProvinceCode or None,
            "addressCityCode": body.agencyAddressCityCode or None,
            "addressBarangayCode": body.agencyAddressBarangayCode or None,
            "website": (body.agencyWebsite or "").strip() or None,
            "contactEmail": body.agencyEmail.strip(),
            "contactPhone": body.agencyPhone.strip(),
            "registrationStatus": "PENDING",
            "accountStatus": "INACTIVE",
            "subscriptionStatus": "ACTIVE",
            "createdBy": user_id,
            "createdAt": _now(),
        }, ["addressRegionCode", "addressProvinceCode", "addressCityCode", "addressBarangayCode"])
        agency_id = agency["id"]
        await supabase_db.update("user", user_id, {"agencyId": agency_id})
    except (supabase_db.DatabaseError, supabase_db.DatabaseNotConfigured) as exc:
        # Three writes, no transaction: undo what was created so the email is not left taken.
        for table, row_id in (("agency", agency_id), ("user", user_id)):
            if row_id is not None:
                try:
                    await supabase_db.delete(table, row_id)
                except supabase_db.DatabaseError as cleanup:
                    logger.error(f"[auth] registration rollback could not remove {table} {row_id}: {cleanup}")
        if "23505" in str(exc) or "duplicate key" in str(exc):
            raise HTTPException(409, "This organization or email is already registered.") from exc
        if isinstance(exc, supabase_db.DatabaseNotConfigured):
            raise HTTPException(503, str(exc)) from exc
        logger.error(f"[auth] registration failed: {exc}")
        raise HTTPException(502, "The registration could not be saved. Try again.") from exc
    return {"agencyId": agency_id, "userId": user_id}


# ── Staff accounts ───────────────────────────────────────────────────────────

class CreateStaffRequest(BaseModel):
    firstName: str = Field(min_length=1, max_length=100)
    lastName: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    phone: str | None = Field(default=None, max_length=40)
    password: str = Field(min_length=1, max_length=200)
    role: str = Field(pattern=r"^(COMMAND_STAFF|FIELD_RESPONDER)$")


@router.post("/users", status_code=201)
async def create_staff(body: CreateStaffRequest, user: auth.Principal = Depends(require_roles("AGENCY_ADMIN"))) -> dict:
    if user.db_id is None or not (user.agency_id or "").isdigit():
        raise HTTPException(403, "Demo accounts cannot create real users.")
    problem = auth.password_problem(body.password)
    if problem:
        raise HTTPException(422, problem)
    if await _run(_user_by_email(body.email)):
        raise HTTPException(409, "A user with this email address already exists.")
    rows = await _run(supabase_db.insert("user", {
        "email": body.email.strip(),
        "passwordHash": auth.hash_password(body.password),
        "firstName": body.firstName.strip(),
        "lastName": body.lastName.strip(),
        "phone": (body.phone or "").strip() or None,
        "role": body.role,
        # Always the admin's own agency, whatever the browser sends.
        "agencyId": int(user.agency_id),
        "active": True,
        "createdAt": _now(),
    }))
    return {"userId": rows[0]["id"]}


# ── Own password ─────────────────────────────────────────────────────────────

class ChangePasswordRequest(BaseModel):
    currentPassword: str = Field(min_length=1, max_length=200)
    newPassword: str = Field(min_length=1, max_length=200)


@router.post("/password", status_code=204, response_class=Response)
async def change_password(body: ChangePasswordRequest, user: auth.Principal = Depends(current_user)) -> Response:
    if user.db_id is None:
        raise HTTPException(403, "Demo account passwords cannot be changed.")
    rows = await _run(supabase_db.select("user", id=user.db_id))
    if not rows or not auth.verify_password(body.currentPassword, rows[0].get("passwordHash"))[0]:
        raise HTTPException(400, "Current password is incorrect.")
    problem = auth.password_problem(body.newPassword)
    if problem:
        raise HTTPException(422, problem)
    await _run(supabase_db.update("user", user.db_id, {"passwordHash": auth.hash_password(body.newPassword)}))
    return Response(status_code=204)
