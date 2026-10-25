"""
Alert and Notification Management - the rules that must hold regardless of
which SMS or push provider is behind them:

  * only an incident that exists (i.e. was verified) can be dispatched
  * every recipient gets SMS, PUSH and DASHBOARD alerts
  * a failed SMS is marked FAILED and the other channels still go out
  * every alert and every status change is written to audit_history
  * the message carries type/label, priority, description and GPS in <= 300 chars
  * status only moves forward (SENT -> DELIVERED -> READ; FAILED is final)

The database, providers and WebSocket are replaced with in-memory fakes.
"""
import asyncio

import pytest

from services import alert_service, live_hub, push_gateway, supabase_db
from services.sms_gateway import SendResult, normalize_ph_number

INCIDENT = {
    "id": 7, "agencyId": 1, "incidentType": "FIRE", "severity": "CRITICAL", "status": "OPEN",
    "lat": 10.315701, "lng": 123.885403, "description": "Two-storey house, smoke from the roof",
}
RESPONDER = {"id": 21, "role": "FIELD_RESPONDER", "active": True, "agencyId": 1, "phone": "+63 917 123 4567"}


class FakeDb:
    def __init__(self):
        self.tables = {"incident": [dict(INCIDENT)], "user": [dict(RESPONDER)], "alert": [], "response": [], "audit_history": []}
        self._ids = {}

    async def select(self, table, **filters):
        rows = self.tables[table]
        for column, value in filters.items():
            if column in ("order", "limit"):
                continue
            wanted = set(value) if isinstance(value, (list, tuple)) else {value}
            rows = [r for r in rows if r.get(column) in wanted]
        return [dict(r) for r in rows]

    async def insert(self, table, rows):
        rows = rows if isinstance(rows, list) else [rows]
        out = []
        for row in rows:
            self._ids[table] = self._ids.get(table, 0) + 1
            stored = {"id": self._ids[table], **row}
            self.tables[table].append(stored)
            out.append(dict(stored))
        return out

    async def update(self, table, row_id, patch):
        for row in self.tables[table]:
            if row["id"] == row_id:
                row.update(patch)
                return dict(row)
        return None


class FakeSms:
    def __init__(self, ok=True):
        self.ok = ok
        self.sent = []

    async def send(self, number, message):
        self.sent.append((number, message))
        return SendResult(ok=self.ok, provider_id="sms-1" if self.ok else None, error=None if self.ok else "boom")

    async def delivery_state(self, provider_id):
        return "DELIVERED"


@pytest.fixture
def env(monkeypatch):
    db = FakeDb()
    broadcasts = []
    monkeypatch.setattr(supabase_db, "select", db.select)
    monkeypatch.setattr(supabase_db, "insert", db.insert)
    monkeypatch.setattr(supabase_db, "update", db.update)

    async def broadcast(message, agency_id=None):
        broadcasts.append(message)

    monkeypatch.setattr(live_hub, "broadcast", broadcast)
    # Delivery follow-ups sleep for seconds; tests check the immediate outcome only.
    monkeypatch.setattr(asyncio, "create_task", lambda coro: coro.close())
    return db, broadcasts


def _use_sms(monkeypatch, gateway):
    monkeypatch.setattr(alert_service, "get_sms_gateway", lambda: gateway)


def test_dispatch_sends_all_three_channels_and_audits(env, monkeypatch):
    db, broadcasts = env
    sms = FakeSms()
    _use_sms(monkeypatch, sms)

    alerts = asyncio.run(alert_service.dispatch(7, [21], dispatched_by=3, label="Major Fire Damage"))

    assert sorted(a["alertType"] for a in alerts) == ["DASHBOARD", "PUSH", "SMS"]
    assert sms.sent and sms.sent[0][0] == "09171234567"
    # No push token registered, so PUSH fails while SMS and DASHBOARD stay SENT.
    by_type = {a["alertType"]: a for a in alerts}
    assert by_type["SMS"]["status"] == "SENT"
    assert by_type["DASHBOARD"]["status"] == "SENT"
    assert by_type["PUSH"]["status"] == "FAILED"
    assert all(a["sentAt"].endswith("Z") for a in alerts)

    audit = db.tables["audit_history"]
    assert all(entry["entityType"] == "ALERT" for entry in audit)
    assert {e["entityId"] for e in audit if e["newValue"] == "SENT"} == {a["id"] for a in alerts}
    assert db.tables["response"][0]["responseStatus"] == "ASSIGNED"
    assert db.tables["incident"][0]["status"] == "ASSIGNED"
    assert any(b["type"] == "alert" for b in broadcasts)


def test_failed_sms_still_delivers_push_and_dashboard(env, monkeypatch):
    db, _ = env
    db.tables["user"][0]["pushToken"] = "ExponentPushToken[abc]"
    _use_sms(monkeypatch, FakeSms(ok=False))

    async def push_ok(token, title, body, data):
        return SendResult(ok=True, provider_id="ticket-1")

    monkeypatch.setattr(push_gateway, "send", push_ok)

    alerts = asyncio.run(alert_service.dispatch(7, [21], dispatched_by=3))
    by_type = {a["alertType"]: a["status"] for a in alerts}
    assert by_type == {"SMS": "FAILED", "PUSH": "SENT", "DASHBOARD": "SENT"}


def test_only_existing_incidents_can_be_dispatched(env, monkeypatch):
    _use_sms(monkeypatch, FakeSms())
    with pytest.raises(alert_service.AlertNotFound):
        asyncio.run(alert_service.dispatch(999, [21], dispatched_by=3))


def test_recipient_must_be_active_responder_of_same_agency(env, monkeypatch):
    db, _ = env
    _use_sms(monkeypatch, FakeSms())
    db.tables["user"][0]["agencyId"] = 2
    with pytest.raises(alert_service.AlertError):
        asyncio.run(alert_service.dispatch(7, [21], dispatched_by=3))


def test_mark_read_sets_read_and_acknowledged(env, monkeypatch):
    db, _ = env
    _use_sms(monkeypatch, FakeSms())
    alerts = asyncio.run(alert_service.dispatch(7, [21], dispatched_by=3))
    dashboard = next(a for a in alerts if a["alertType"] == "DASHBOARD")

    read = asyncio.run(alert_service.mark_read(dashboard["id"], 21))
    assert read["status"] == "READ"
    assert read["acknowledgedAt"]
    assert any(e["fieldChanged"] == "acknowledgedAt" and e["entityId"] == dashboard["id"] for e in db.tables["audit_history"])

    with pytest.raises(alert_service.AlertError):
        asyncio.run(alert_service.mark_read(dashboard["id"], 99))


def test_status_never_moves_backward(env):
    db, _ = env
    alert = asyncio.run(supabase_db.insert("alert", {"status": "READ", "message": "x"}))[0]
    unchanged = asyncio.run(alert_service.set_status(alert, "DELIVERED", 1))
    assert unchanged["status"] == "READ"
    failed = asyncio.run(supabase_db.insert("alert", {"status": "FAILED", "message": "x"}))[0]
    assert asyncio.run(alert_service.set_status(failed, "DELIVERED", 1))["status"] == "FAILED"


def test_message_has_type_label_priority_description_gps_and_fits():
    message = alert_service.compose_message(INCIDENT, "Major Fire Damage")
    assert "CRITICAL" in message
    assert "Fire: Major Fire Damage" in message
    assert "smoke from the roof" in message
    assert "10.31570, 123.88540" in message
    assert len(message) <= 300

    long = alert_service.compose_message({**INCIDENT, "description": "x " * 400})
    assert len(long) <= 300
    assert "GPS:" in long  # the location is never what gets cut


def test_casualty_label_defaults():
    message = alert_service.compose_message({**INCIDENT, "incidentType": "VICTIM_DETECTED", "description": None})
    assert "Victim: Casualty Detected" in message


@pytest.mark.parametrize("raw,expected", [
    ("+63 917 123 4567", "09171234567"),
    ("639171234567", "09171234567"),
    ("09171234567", "09171234567"),
    ("9171234567", "09171234567"),
    ("12345", None),
    (None, None),
])
def test_ph_number_normalization(raw, expected):
    assert normalize_ph_number(raw) == expected


# ── SMS provider selection ───────────────────────────────────────────────────

from services import sms_gateway


def test_textbee_selected_when_configured(monkeypatch):
    monkeypatch.setenv("SMS_PROVIDER", "textbee")
    monkeypatch.setenv("TEXTBEE_API_KEY", "key")
    monkeypatch.setenv("TEXTBEE_DEVICE_ID", "device")
    assert isinstance(sms_gateway.get_sms_gateway(), sms_gateway.TextbeeGateway)


def test_textbee_without_credentials_fails_instead_of_pretending(monkeypatch):
    monkeypatch.setenv("SMS_PROVIDER", "textbee")
    monkeypatch.delenv("TEXTBEE_API_KEY", raising=False)
    monkeypatch.delenv("TEXTBEE_DEVICE_ID", raising=False)
    result = asyncio.run(sms_gateway.get_sms_gateway().send("09171234567", "hi"))
    assert result.ok is False
    assert "TEXTBEE_API_KEY" in result.error


def test_textbee_sends_e164_number_with_api_key(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 201
        text = ""

        def json(self):
            return {"data": {"success": True, "smsBatchId": "b1"}}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json, headers):
            captured.update(url=url, json=json, headers=headers)
            return FakeResponse()

    monkeypatch.setattr(sms_gateway.httpx, "AsyncClient", FakeClient)
    gateway = sms_gateway.TextbeeGateway("key", "dev1", "https://api.textbee.dev/api/v1")
    result = asyncio.run(gateway.send("09171234567", "alert"))

    assert result.ok is True
    assert captured["url"] == "https://api.textbee.dev/api/v1/gateway/devices/dev1/send-sms"
    assert captured["json"] == {"recipients": ["+639171234567"], "message": "alert"}
    assert captured["headers"]["x-api-key"] == "key"
