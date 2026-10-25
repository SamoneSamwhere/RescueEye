"""
Alert and Notification Management.

Trigger: Command Staff dispatch a *verified* incident to one or more Field
Responders. Incidents only exist in the database once a detection has been
verified, so raw AI output can never reach this code - there is no path from a
detection straight to an alert.

On dispatch, each responder gets three alert rows, one per channel:
  SMS        via the SMS gateway (reaches phones with no data coverage)
  PUSH       via Expo push (phones with a data connection and a registered token)
  DASHBOARD  the record shown in the responder's in-app notification history
The channels are independent: a failed SMS is marked FAILED and the PUSH and
DASHBOARD alerts still go out.

Status: SENT on creation -> DELIVERED or FAILED as the provider reports back ->
READ when the responder opens it. Every change is written to the alert row,
logged to audit_history (EntityType ALERT) and broadcast over the live
WebSocket so Command Staff see delivery as it happens.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from services import live_hub, push_gateway, supabase_db
from services.sms_gateway import get_sms_gateway, normalize_ph_number

logger = logging.getLogger("rescueeye.alerts")

MAX_MESSAGE_LENGTH = 300
CHANNELS = ("SMS", "PUSH", "DASHBOARD")

INCIDENT_TYPE_NAME = {
    "VICTIM_DETECTED": "Victim",
    "FIRE": "Fire",
    "FLOOD": "Flood",
    "STRUCTURAL": "Structural",
    "UNKNOWN": "Unclassified",
}
DEFAULT_LABEL = {
    "VICTIM_DETECTED": "Casualty Detected",
    "FIRE": "Fire Damage",
    "FLOOD": "Flood Damage",
    "STRUCTURAL": "Structural Damage",
    "UNKNOWN": "Incident Reported",
}

# Progress order; FAILED is terminal and READ is the end of the happy path.
_RANK = {"SENT": 0, "DELIVERED": 1, "READ": 2}

# Seconds after sending at which the provider is asked whether it delivered.
SMS_CHECKS_S = (10, 30, 60, 120, 300)
PUSH_CHECKS_S = (15, 60, 300)


class AlertError(ValueError):
    """A dispatch or update the caller asked for that is not allowed."""


class AlertForbidden(Exception):
    """The caller may not act on this alert or incident."""


class AlertNotFound(LookupError):
    pass


def _now() -> str:
    # The schema uses `timestamp without time zone` holding UTC.
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="milliseconds")


def _utc(value: str | None) -> str | None:
    """DB timestamps carry no zone; mark them UTC so browsers do not read them as local time."""
    if not value or value.endswith("Z") or "+" in value[10:]:
        return value
    return value + "Z"


def to_client(alert: dict) -> dict:
    return {
        **alert,
        "sentAt": _utc(alert.get("sentAt")),
        "acknowledgedAt": _utc(alert.get("acknowledgedAt")),
        "updatedAt": _utc(alert.get("updatedAt")),
    }


# ── Message ──────────────────────────────────────────────────────────────────

def compose_message(incident: dict, label: str | None = None) -> str:
    """
    Incident type and full label, priority, description and GPS position, in at
    most 300 characters. Plain ASCII so an SMS stays in the GSM charset (a
    single non-GSM character switches the whole message to 70-char segments).
    """
    incident_type = incident.get("incidentType") or "UNKNOWN"
    type_name = INCIDENT_TYPE_NAME.get(incident_type, "Unclassified")
    full_label = (label or "").strip()[:60] or DEFAULT_LABEL.get(incident_type, "Incident Reported")
    severity = incident.get("severity") or "UNKNOWN"

    head = f"RescueEye {severity} ALERT - {type_name}: {full_label}."
    gps = f"GPS: {float(incident['lat']):.5f}, {float(incident['lng']):.5f}."
    tail = "Open RescueEye to accept or decline."

    description = " ".join((incident.get("description") or "").split())
    fixed = len(head) + len(gps) + len(tail) + 2  # spaces between parts
    if description:
        room = MAX_MESSAGE_LENGTH - fixed - 1
        if room <= 3:
            description = ""
        elif len(description) > room:
            description = description[: room - 3].rstrip() + "..."
        elif not description.endswith((".", "!", "?")):
            description = (description + ".")[:room]

    parts = [head, description, gps, tail] if description else [head, gps, tail]
    message = " ".join(parts)
    return message[:MAX_MESSAGE_LENGTH]


# ── Persistence helpers ──────────────────────────────────────────────────────

async def _audit(alert_id: int, field: str, old: str | None, new: str | None, actor_id: int) -> None:
    try:
        await supabase_db.insert("audit_history", {
            "entityType": "ALERT",
            "entityId": alert_id,
            "fieldChanged": field,
            "oldValue": old,
            "newValue": new,
            "changedBy": actor_id,
            "changedByType": "USER",
            "changedAt": _now(),
        })
    except supabase_db.DatabaseError:
        # The alert itself already went out; a lost audit line must not undo it.
        logger.exception(f"[alerts] audit write failed for alert {alert_id}")


# incident id -> agency id, so a live alert update reaches only that agency's screens.
_incident_agency: dict[int, str] = {}


async def incident_agency(incident_id: int) -> str | None:
    if incident_id not in _incident_agency:
        rows = await supabase_db.select("incident", id=incident_id)
        if not rows:
            return None
        _incident_agency[incident_id] = str(rows[0]["agencyId"])
    return _incident_agency[incident_id]


async def _publish(alert: dict) -> None:
    agency = await incident_agency(alert["incidentId"])
    await live_hub.broadcast({"type": "alert", "alert": to_client(alert)}, agency)


async def set_status(alert: dict, new_status: str, actor_id: int, *, acknowledge: bool = False) -> dict:
    """Moves an alert forward (never backward), audits each changed field, and broadcasts it."""
    old_status = alert["status"]
    patch: dict = {}
    if old_status != new_status:
        allowed = old_status != "FAILED" and (
            new_status == "FAILED" and old_status != "READ"
            or _RANK.get(new_status, -1) > _RANK.get(old_status, -1)
        )
        if allowed:
            patch["status"] = new_status
    if acknowledge and not alert.get("acknowledgedAt"):
        patch["acknowledgedAt"] = _now()
    if not patch:
        return alert

    patch["updatedAt"] = _now()
    updated = await supabase_db.update("alert", alert["id"], patch) or {**alert, **patch}
    if "status" in patch:
        await _audit(alert["id"], "status", old_status, patch["status"], actor_id)
    if "acknowledgedAt" in patch:
        await _audit(alert["id"], "acknowledgedAt", None, patch["acknowledgedAt"], actor_id)
    await _publish(updated)
    return updated


# ── Delivery ─────────────────────────────────────────────────────────────────

async def _follow_delivery(alert: dict, check, provider_id: str, schedule: tuple[int, ...], actor_id: int) -> None:
    """Asks the provider until it settles DELIVERED or FAILED, then records that once."""
    waited = 0
    for at in schedule:
        await asyncio.sleep(at - waited)
        waited = at
        try:
            state = await check(provider_id)
        except Exception:  # noqa: BLE001 - a status lookup failing is retried at the next check
            logger.warning(f"[alerts] delivery check failed for alert {alert['id']}", exc_info=True)
            continue
        if state != "SENT":
            current = (await supabase_db.select("alert", id=alert["id"]))
            await set_status(current[0] if current else alert, state, actor_id)
            return


async def _deliver_sms(alert: dict, phone: str | None, actor_id: int) -> dict:
    number = normalize_ph_number(phone)
    if not number:
        logger.info(f"[alerts] SMS alert {alert['id']} failed: no valid mobile number on file")
        return await set_status(alert, "FAILED", actor_id)
    gateway = get_sms_gateway()
    result = await gateway.send(number, alert["message"])
    if not result.ok:
        logger.warning(f"[alerts] SMS alert {alert['id']} failed: {result.error}")
        return await set_status(alert, "FAILED", actor_id)
    if result.provider_id:
        asyncio.create_task(_follow_delivery(alert, gateway.delivery_state, result.provider_id, SMS_CHECKS_S, actor_id))
    return alert


async def _deliver_push(alert: dict, token: str | None, actor_id: int) -> dict:
    if not push_gateway.is_expo_token(token):
        logger.info(f"[alerts] PUSH alert {alert['id']} failed: responder has no registered device")
        return await set_status(alert, "FAILED", actor_id)
    result = await push_gateway.send(
        token, "RescueEye mission alert", alert["message"],
        {"incidentId": alert["incidentId"], "alertId": alert["id"]},
    )
    if not result.ok:
        logger.warning(f"[alerts] PUSH alert {alert['id']} failed: {result.error}")
        return await set_status(alert, "FAILED", actor_id)
    if result.provider_id:
        asyncio.create_task(_follow_delivery(alert, push_gateway.delivery_state, result.provider_id, PUSH_CHECKS_S, actor_id))
    return alert


# ── Public operations ────────────────────────────────────────────────────────

async def dispatch(incident_id: int, recipient_ids: list[int], dispatched_by: int, label: str | None = None,
                   *, agency_id: str | None = None) -> list[dict]:
    """
    Records the assignment and sends SMS, PUSH and DASHBOARD alerts to every recipient.
    `agency_id` is the dispatcher's agency; the incident must belong to it.
    """
    incidents = await supabase_db.select("incident", id=incident_id)
    if not incidents:
        raise AlertNotFound(f"incident {incident_id} not found - only verified incidents can be dispatched")
    incident = incidents[0]
    if agency_id is not None and str(incident["agencyId"]) != str(agency_id):
        raise AlertForbidden(f"incident {incident_id} belongs to another agency")
    _incident_agency[incident_id] = str(incident["agencyId"])
    if incident["status"] == "RESOLVED":
        raise AlertError(f"incident {incident_id} is resolved")

    recipient_ids = list(dict.fromkeys(recipient_ids))
    if not recipient_ids:
        raise AlertError("no recipients")
    users = {u["id"]: u for u in await supabase_db.select("user", id=recipient_ids)}
    for uid in recipient_ids:
        user = users.get(uid)
        if not user:
            raise AlertNotFound(f"user {uid} not found")
        if user["role"] != "FIELD_RESPONDER" or not user["active"]:
            raise AlertError(f"user {uid} is not an active Field Responder")
        if user["agencyId"] != incident["agencyId"]:
            raise AlertError(f"user {uid} belongs to a different agency than incident {incident_id}")

    now = _now()
    await supabase_db.insert("response", [
        {"incidentId": incident_id, "userId": uid, "responseStatus": "ASSIGNED", "assignedAt": now, "updatedAt": now}
        for uid in recipient_ids
    ])
    if incident["status"] == "OPEN":
        await supabase_db.update("incident", incident_id, {"status": "ASSIGNED", "updatedAt": now})

    message = compose_message(incident, label)
    rows = await supabase_db.insert("alert", [
        {"incidentId": incident_id, "recipientId": uid, "alertType": channel, "message": message,
         "status": "SENT", "sentAt": now, "updatedAt": now}
        for uid in recipient_ids
        for channel in CHANNELS
    ])
    for row in rows:
        await _audit(row["id"], "status", None, "SENT", dispatched_by)
        await _publish(row)

    async def deliver(row: dict) -> dict:
        user = users[row["recipientId"]]
        if row["alertType"] == "SMS":
            return await _deliver_sms(row, user.get("phone"), dispatched_by)
        if row["alertType"] == "PUSH":
            return await _deliver_push(row, user.get("pushToken"), dispatched_by)
        return row  # DASHBOARD: delivered by the history endpoint and the live socket

    delivered = await asyncio.gather(*(deliver(row) for row in rows))
    logger.info(f"[alerts] incident {incident_id}: {len(rows)} alerts to {len(recipient_ids)} responder(s)")
    return [to_client(a) for a in delivered]


async def list_alerts(recipient_id: int | None = None, incident_id: int | None = None) -> list[dict]:
    filters: dict = {"order": "sentAt.desc", "limit": 500}
    if recipient_id is not None:
        filters["recipientId"] = recipient_id
    if incident_id is not None:
        filters["incidentId"] = incident_id
    return [to_client(a) for a in await supabase_db.select("alert", **filters)]


async def mark_read(alert_id: int, user_id: int) -> dict:
    """The responder opened the alert: READ, and acknowledged if it was not already."""
    rows = await supabase_db.select("alert", id=alert_id)
    if not rows:
        raise AlertNotFound(f"alert {alert_id} not found")
    alert = rows[0]
    if alert["recipientId"] != user_id:
        raise AlertError("only the recipient can mark an alert read")
    return to_client(await set_status(alert, "READ", user_id, acknowledge=True))


async def acknowledge(incident_id: int, user_id: int) -> list[dict]:
    """The responder accepted or declined the mission: stamp acknowledgedAt on their alerts for it."""
    rows = await supabase_db.select("alert", incidentId=incident_id, recipientId=user_id)
    updated = [await set_status(row, row["status"], user_id, acknowledge=True) for row in rows]
    return [to_client(a) for a in updated]


async def register_push_token(user_id: int, token: str) -> None:
    if not push_gateway.is_expo_token(token):
        raise AlertError("not an Expo push token")
    if not await supabase_db.update("user", user_id, {"pushToken": token}):
        raise AlertNotFound(f"user {user_id} not found")
