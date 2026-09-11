import asyncio
import selectors
import sys
import uuid
from getpass import getpass

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.domains.auth import entities
from app.domains.auth.repository import UserRepository
from app.domains.rbac.repository import RoleRepository

# Seed defaults — used when ADMIN_EMAIL / ADMIN_PASSWORD aren't set (in the
# environment or .env) and the prompt is left blank. Fine for local/dev
# bootstrapping; set real values in .env for anything else.
DEFAULT_ADMIN_EMAIL = "admin@example.com"
DEFAULT_ADMIN_PASSWORD = "admin12345"


async def main() -> None:
    # settings reads both the process environment and .env (unlike os.environ,
    # which never sees .env).
    email = (
        settings.admin_email
        or input(f"Admin email [{DEFAULT_ADMIN_EMAIL}]: ").strip()
        or DEFAULT_ADMIN_EMAIL
    )
    password = (
        settings.admin_password
        or getpass(f"Admin password [{DEFAULT_ADMIN_PASSWORD}]: ")
        or DEFAULT_ADMIN_PASSWORD
    )
    first_name = settings.admin_first_name
    last_name = settings.admin_last_name
    contact_number = settings.admin_contact_number

    async with AsyncSessionLocal() as db:
        users = UserRepository(db)

        if await users.get_by_email(email) is not None:
            print(f"A user with email '{email}' already exists.", file=sys.stderr)
            sys.exit(1)

        admin_role = await RoleRepository(db).get_by_name("admin")
        if admin_role is None:
            print("'admin' role is not seeded — run migrations first.", file=sys.stderr)
            sys.exit(1)

        user_id = uuid.uuid4()
        await users.add(
            entities.User(
                id=user_id,
                first_name=first_name,
                middle_initial=None,
                last_name=last_name,
                contact_number=contact_number,
                email=email,
                password_hash=hash_password(password),
                role_id=admin_role.id,
                role=admin_role.name,
                resume_object_key=None,
            )
        )
        await db.commit()
        user = await users.get_by_id(user_id)
        print(f"Created admin user {user.email} (id={user.id})")


if __name__ == "__main__":
    # psycopg's async driver can't run under Windows' default ProactorEventLoop
    # (asyncio.run()'s default there) — force the selector-based loop instead.
    asyncio.run(
        main(),
        loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
    )
