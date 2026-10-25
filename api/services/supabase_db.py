"""
Minimal async client for the Supabase PostgREST API.

The alert module is the first part of this service that reads and writes the
platform database (incident, user, response, alert, audit_history). PostgREST
over httpx keeps that to one existing dependency rather than adding a Postgres
driver. Column names are the database's own camelCase (Prisma-managed schema).

Configured with SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY. The service-role
key is server-only - it must never be shipped to the browser.
"""
from __future__ import annotations

import os
from typing import Any

import httpx


class DatabaseNotConfigured(RuntimeError):
    pass


class DatabaseError(RuntimeError):
    pass


def _config() -> tuple[str, str]:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise DatabaseNotConfigured("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in api/.env")
    return url, key


async def _request(method: str, table: str, *, params: dict | None = None, json: Any = None,
                   prefer: str | None = None) -> Any:
    url, key = _config()
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        headers["Prefer"] = prefer
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.request(method, f"{url}/rest/v1/{table}", params=params, json=json, headers=headers)
    if response.status_code >= 400:
        raise DatabaseError(f"{method} {table} failed ({response.status_code}): {response.text[:300]}")
    return response.json() if response.content else None


async def select(table: str, **filters: Any) -> list[dict]:
    """Rows matching every `column=value` filter (PostgREST `eq`); `order`/`limit` pass through."""
    params: dict[str, Any] = {"select": "*"}
    for column, value in filters.items():
        if column in ("order", "limit"):
            params[column] = value
        elif isinstance(value, (list, tuple)):
            params[column] = f"in.({','.join(str(v) for v in value)})"
        else:
            params[column] = f"eq.{value}"
    return await _request("GET", table, params=params)


async def insert(table: str, rows: dict | list[dict]) -> list[dict]:
    return await _request("POST", table, json=rows, prefer="return=representation")


async def update(table: str, row_id: int, patch: dict) -> dict | None:
    rows = await _request("PATCH", table, params={"id": f"eq.{row_id}"}, json=patch, prefer="return=representation")
    return rows[0] if rows else None


async def select_raw(table: str, params: dict[str, Any]) -> list[dict]:
    """A GET with PostgREST query params as given, for filters `select` can't express (ilike, or, ...)."""
    return await _request("GET", table, params=params)


async def delete(table: str, row_id: int) -> None:
    await _request("DELETE", table, params={"id": f"eq.{row_id}"})


def postgrest_escape_like(value: str) -> str:
    """A literal for a PostgREST `ilike` filter: `*` is its wildcard, `%`/`_` are Postgres's."""
    return value.replace("\\", "\\\\").replace("%", "\%").replace("_", "\_").replace("*", "\*")


async def upsert(table: str, rows: dict | list[dict]) -> list[dict]:
    """Insert, or replace the row with the same primary key."""
    return await _request("POST", table, json=rows, prefer="resolution=merge-duplicates,return=representation")
