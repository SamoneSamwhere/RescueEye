"""
Alert endpoints (see services/alert_service.py for the delivery rules).

POST /alerts/dispatch           Command Staff dispatched a verified incident: record the
                                assignment and send SMS + PUSH + DASHBOARD alerts.
GET  /alerts?recipientId=&incidentId=
                                Alert history - a responder's own, or one incident's.
POST /alerts/{id}/read          The responder opened the alert: READ + acknowledgedAt.
POST /alerts/acknowledge        The responder accepted or declined: acknowledgedAt on
                                their alerts for that incident.
POST /alerts/push-token         A responder's device registers its Expo push token.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from routers.deps import current_user, require_roles
from services import alert_service, auth, supabase_db

router = APIRouter()


class DispatchRequest(BaseModel):
    incidentId: int
    recipientIds: list[int] = Field(min_length=1)
    dispatchedBy: int
    # Full human label, e.g. "Major Fire Damage"; derived from the incident type when omitted.
    label: str | None = Field(default=None, max_length=60)


class ReadRequest(BaseModel):
    userId: int


class AcknowledgeRequest(BaseModel):
    incidentId: int
    userId: int


class PushTokenRequest(BaseModel):
    userId: int
    token: str = Field(min_length=1, max_length=255)


async def _run(coro):
    try:
        return await coro
    except supabase_db.DatabaseNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc
    except supabase_db.DatabaseError as exc:
        raise HTTPException(502, str(exc)) from exc
    except alert_service.AlertNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except alert_service.AlertForbidden as exc:
        raise HTTPException(403, str(exc)) from exc
    except alert_service.AlertError as exc:
        raise HTTPException(422, str(exc)) from exc


def _real_id(user: auth.Principal) -> int:
    if user.db_id is None:
        raise HTTPException(403, "Demo accounts cannot send or read real alerts.")
    return user.db_id


@router.post("/dispatch")
async def dispatch(body: DispatchRequest, user: auth.Principal = Depends(require_roles("COMMAND_STAFF"))) -> dict:
    # The dispatcher is whoever is signed in, whatever the body claims.
    alerts = await _run(alert_service.dispatch(
        body.incidentId, body.recipientIds, _real_id(user), body.label, agency_id=user.agency_id,
    ))
    return {"alerts": alerts}


@router.get("")
async def list_alerts(
    recipientId: int | None = None, incidentId: int | None = None, user: auth.Principal = Depends(current_user),
) -> dict:
    if recipientId is None and incidentId is None:
        raise HTTPException(422, "pass recipientId or incidentId")
    if user.role == "FIELD_RESPONDER" and recipientId != _real_id(user):
        raise HTTPException(403, "You can only see your own alerts.")
    if incidentId is not None and await _run(alert_service.incident_agency(incidentId)) != user.agency_id:
        raise HTTPException(403, "This incident belongs to another agency.")
    if recipientId is not None and user.role != "FIELD_RESPONDER":
        rows = await _run(supabase_db.select("user", id=recipientId))
        if not rows or str(rows[0].get("agencyId")) != user.agency_id:
            raise HTTPException(403, "This responder belongs to another agency.")
    return {"alerts": await _run(alert_service.list_alerts(recipientId, incidentId))}


@router.post("/{alert_id}/read")
async def mark_read(alert_id: int, body: ReadRequest, user: auth.Principal = Depends(current_user)) -> dict:
    return await _run(alert_service.mark_read(alert_id, _real_id(user)))


@router.post("/acknowledge")
async def acknowledge(body: AcknowledgeRequest, user: auth.Principal = Depends(current_user)) -> dict:
    return {"alerts": await _run(alert_service.acknowledge(body.incidentId, _real_id(user)))}


@router.post("/push-token", status_code=204, response_class=Response)
async def register_push_token(body: PushTokenRequest, user: auth.Principal = Depends(current_user)) -> Response:
    await _run(alert_service.register_push_token(_real_id(user), body.token))
    return Response(status_code=204)
