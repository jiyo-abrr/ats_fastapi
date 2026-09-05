import os
import sys
import uuid
from getpass import getpass

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.domains.auth import entities
from app.domains.auth.repository import UserRepository
from app.domains.rbac.repository import RoleRepository


def main() -> None:
    email = os.environ.get("ADMIN_EMAIL") or input("Admin email: ").strip()
    password = os.environ.get("ADMIN_PASSWORD") or getpass("Admin password: ")
    first_name = os.environ.get("ADMIN_FIRST_NAME", "Admin")
    last_name = os.environ.get("ADMIN_LAST_NAME", "User")
    contact_number = os.environ.get("ADMIN_CONTACT_NUMBER", "N/A")

    db = SessionLocal()
    try:
        users = UserRepository(db)

        if users.get_by_email(email) is not None:
            print(f"A user with email '{email}' already exists.", file=sys.stderr)
            sys.exit(1)

        admin_role = RoleRepository(db).get_by_name("admin")
        if admin_role is None:
            print(
                "'admin' role is not seeded — run migrations first.", file=sys.stderr
            )
            sys.exit(1)

        user_id = uuid.uuid4()
        users.add(
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
        db.commit()
        user = users.get_by_id(user_id)
        print(f"Created admin user {user.email} (id={user.id})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
