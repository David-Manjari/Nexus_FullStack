"""User credential authentication."""

from werkzeug.security import check_password_hash

from .admin_accounts import connect_database


class AuthenticationError(ValueError):
    """An expected login failure with a user-facing message and status."""

    def __init__(self, message, status_code=401):
        super().__init__(message)
        self.status_code = status_code


def authenticate_user(identifier, password, *, database_url=None):
    """Return a safe user record if the username/email and password are valid."""
    if not isinstance(identifier, str) or not identifier.strip():
        return None
    if not isinstance(password, str) or not password:
        return None

    identifier = identifier.strip()
    with connect_database(database_url) as connection:
        user = connection.execute(
            """
            SELECT user_id, username, email, password_hash, role, is_active
            FROM "Users"
            WHERE username = %s OR email = %s
            LIMIT 1
            """,
            (identifier, identifier),
        ).fetchone()

    if user is None:
        raise AuthenticationError(
            "No account is configured for that username or email. Contact an administrator."
        )
    if not user["is_active"]:
        raise AuthenticationError(
            "This account is inactive. Contact an administrator.", 403
        )
    if not check_password_hash(user["password_hash"], password):
        raise AuthenticationError("The password is incorrect.")

    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "email": user["email"],
        "role": user["role"],
    }
