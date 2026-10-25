"""
Set any account's password from the server, stored as bcrypt.

For the System Admin (who has no admin above them to reset it), for an
account locked out of its old password, and for seeding pilot accounts.
Uses api/.env's SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.

    cd api
    .venv/Scripts/python.exe -m scripts.admin.set_password admin@rescueeye.io
    (prompts for the new password twice; nothing is echoed)
"""
from __future__ import annotations

import asyncio
import getpass
import sys

from dotenv import load_dotenv

load_dotenv()

from services import auth, supabase_db  # noqa: E402 - needs the env loaded first


async def main(email: str) -> int:
    rows = await supabase_db.select_raw("user", {
        "select": "id,email,role,active",
        "email": f"ilike.{supabase_db.postgrest_escape_like(email.strip())}",
    })
    if not rows:
        print(f"No account with email {email!r}.")
        return 1
    user = rows[0]
    print(f"Account {user['id']}: {user['email']} ({user['role']}, {'active' if user['active'] else 'inactive'})")
    password = getpass.getpass("New password: ")
    if getpass.getpass("Repeat it: ") != password:
        print("The passwords do not match. Nothing changed.")
        return 1
    problem = auth.password_problem(password)
    if problem:
        print(problem, "Nothing changed.")
        return 1
    await supabase_db.update("user", user["id"], {"passwordHash": auth.hash_password(password)})
    print("Password updated.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(asyncio.run(main(sys.argv[1])))
