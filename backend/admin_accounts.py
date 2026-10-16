import argparse
import os
import re
from getpass import getpass

from psycopg import sql
from werkzeug.security import generate_password_hash
from .db import connect_database


ROLES = ("admin", "manager", "store_manager", "staff")
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")
MIN_PASSWORD_LENGTH = 6
BOOTSTRAP_LOCK_ID = 726381942105


def _validate_account(username, email, password, role):
    if not isinstance(username, str) or not username.strip():
        raise ValueError("Username is required.")
    if not isinstance(email, str) or not email.strip():
        raise ValueError("Email is required.")
    if not isinstance(password, str) or not password:
        raise ValueError("Password is required.")
    if role is None or role == "":
        raise ValueError(f"Role is required. Choose one of: {', '.join(ROLES)}.")
    username = username.strip()
    email = email.strip()

    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("Username must be 3-64 characters using only letters, digits, '.', '_' or '-'.")
    if not email or len(email) > 254 or "@" not in email:
        raise ValueError("Enter a valid email address.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if role not in ROLES:
        raise ValueError(f"Role must be one of: {', '.join(ROLES)}.")

    return username, email


def _require_admin(connection, admin_user_id):
    admin = connection.execute(
        'SELECT role, is_active FROM "Users" WHERE user_id = %s',
        (admin_user_id,),
    ).fetchone()
    if admin is None or admin["role"] != "admin" or not admin["is_active"]:
        raise PermissionError("Only an active admin account can manage accounts.")


def _account_by_id(connection, user_id):
    return connection.execute(
        '''SELECT user_id, username, email, role, is_active, last_login_at, created_at
           FROM "Users" WHERE user_id = %s''',
        (user_id,),
    ).fetchone()


def _ensure_active_admin_remains(connection, user_id):
    other_admin = connection.execute(
        '''SELECT 1 FROM "Users"
           WHERE role = 'admin' AND is_active = TRUE AND user_id <> %s
           LIMIT 1''',
        (user_id,),
    ).fetchone()
    if other_admin is None:
        raise ValueError("At least one active admin account must remain.")


def list_accounts(admin_user_id, *, database_url=None):
    """Return safe account fields for an active admin."""
    with connect_database(database_url) as connection:
        _require_admin(connection, admin_user_id)
        return connection.execute(
            '''SELECT user_id, username, email, role, is_active, last_login_at, created_at
               FROM "Users" ORDER BY user_id'''
        ).fetchall()


def get_account(admin_user_id, user_id, *, database_url=None):
    """Return one account's safe fields, or None if it does not exist."""
    with connect_database(database_url) as connection:
        _require_admin(connection, admin_user_id)
        return _account_by_id(connection, user_id)


def create_account(admin_user_id, username, email, password, role, *, database_url=None):
    """Create an account after verifying the requesting user is an admin.

    Call this from the backend handler for the admin-only account creation page.
    The role is checked against the database, rather than trusted from the caller.
    """
    username, email = _validate_account(username, email, password, role)
    with connect_database(database_url) as connection:
        _require_admin(connection, admin_user_id)

        account = connection.execute(
            """
            INSERT INTO "Users" (username, email, password_hash, role)
            VALUES (%s, %s, %s, %s)
            RETURNING user_id, username, email, role
            """,
            (username, email, generate_password_hash(password), role),
        ).fetchone()
        return account


def update_account(admin_user_id, user_id, updates, *, database_url=None):
    """Update safe account fields and optionally set a new password."""
    if not isinstance(updates, dict):
        raise ValueError("A JSON object of account fields is required.")

    allowed_fields = {"username", "email", "password", "role", "is_active"}
    unknown_fields = set(updates) - allowed_fields
    if unknown_fields:
        raise ValueError(f"Unsupported account fields: {', '.join(sorted(unknown_fields))}.")
    if not updates:
        raise ValueError("At least one account field must be provided.")

    changes = {}
    for field in ("username", "email"):
        if field in updates:
            value = updates[field]
            if not isinstance(value, str):
                raise ValueError(f"{field.capitalize()} must be text.")
            value = value.strip()
            if not value:
                raise ValueError(f"{field.capitalize()} cannot be empty.")
            if field == "username":
                if not USERNAME_PATTERN.fullmatch(value):
                    raise ValueError("Username must be 3-64 characters using only letters, digits, '.', '_' or '-'.")
            elif not value or len(value) > 254 or "@" not in value:
                raise ValueError("Enter a valid email address.")
            changes[field] = value

    if "role" in updates:
        if updates["role"] not in ROLES:
            raise ValueError(f"Role must be one of: {', '.join(ROLES)}.")
        changes["role"] = updates["role"]

    if "is_active" in updates:
        if not isinstance(updates["is_active"], bool):
            raise ValueError("is_active must be true or false.")
        changes["is_active"] = updates["is_active"]

    if "password" in updates:
        password = updates["password"]
        if not isinstance(password, str) or not password:
            raise ValueError("Password cannot be empty.")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
        changes["password_hash"] = generate_password_hash(password)

    with connect_database(database_url) as connection:
        _require_admin(connection, admin_user_id)
        account = _account_by_id(connection, user_id)
        if account is None:
            return None

        if account["role"] == "admin" and account["is_active"]:
            next_role = changes.get("role", account["role"])
            next_active = changes.get("is_active", account["is_active"])
            if next_role != "admin" or not next_active:
                _ensure_active_admin_remains(connection, user_id)

        assignments = sql.SQL(", ").join(
            sql.SQL("{} = %s").format(sql.Identifier(field)) for field in changes
        )
        query = sql.SQL(
            '''UPDATE "Users" SET {} WHERE user_id = %s
               RETURNING user_id, username, email, role, is_active, last_login_at, created_at'''
        ).format(assignments)
        return connection.execute(query, (*changes.values(), user_id)).fetchone()


def deactivate_account(admin_user_id, user_id, *, database_url=None):
    """Soft-delete an account, preserving records that reference it."""
    with connect_database(database_url) as connection:
        _require_admin(connection, admin_user_id)
        account = _account_by_id(connection, user_id)
        if account is None:
            return None
        if account["role"] == "admin" and account["is_active"]:
            _ensure_active_admin_remains(connection, user_id)
        return connection.execute(
            '''UPDATE "Users" SET is_active = FALSE WHERE user_id = %s
               RETURNING user_id, username, email, role, is_active, last_login_at, created_at''',
            (user_id,),
        ).fetchone()


def bootstrap_first_admin(username, email, password, *, database_url=None):
    """Create the initial admin once, only if the Users table has no admin yet."""
    username, email = _validate_account(username, email, password, "admin")
    with connect_database(database_url) as connection:
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (BOOTSTRAP_LOCK_ID,))
        existing_admin = connection.execute(
            'SELECT 1 FROM "Users" WHERE role = %s LIMIT 1',
            ("admin",),
        ).fetchone()
        if existing_admin is not None:
            raise RuntimeError("An admin account already exists; bootstrap is disabled.")

        account = connection.execute(
            """
            INSERT INTO "Users" (username, email, password_hash, role)
            VALUES (%s, %s, %s, %s)
            RETURNING user_id, username, email, role
            """,
            (username, email, generate_password_hash(password), "admin"),
        ).fetchone()
        return account


def main():
    parser = argparse.ArgumentParser(
        description="One-time setup for the first admin in the existing Users table."
    )
    parser.add_argument(
        "command",
        choices=("bootstrap-admin",),
        help="Create an initial admin only if no admin exists yet.",
    )
    parser.add_argument("--username", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()

    password = getpass("Initial admin password: ")
    confirmation = getpass("Confirm password: ")
    if password != confirmation:
        parser.error("Passwords do not match.")

    account = bootstrap_first_admin(args.username, args.email, password)
    print(f"Created initial admin account {account['username']} (user ID {account['user_id']}).")


if __name__ == "__main__":
    main()
