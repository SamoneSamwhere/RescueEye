"""A signed-in test client: every endpoint except /auth and /health requires a session token."""
from services import auth

# Command Staff whose user id is also the responder the tests report fixes for,
# so one client can exercise both the console and the device endpoints.
TOKEN = auth.issue_token("usr-1", "COMMAND_STAFF", "agency-1")
AUTH_HEADERS = {"Authorization": f"Bearer {TOKEN}"}
