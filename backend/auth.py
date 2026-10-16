"""Session authentication and role-based route access."""

from functools import wraps

from flask import jsonify, session

from .admin_accounts import connect_database


def roles_required(*allowed_roles):
    """Require a signed-in user whose current database role is allowed."""
    if not allowed_roles:
        raise ValueError("At least one allowed role is required.")

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user_id = session.get("user_id")
            if user_id is None:
                return jsonify(error="Authentication is required."), 401

            with connect_database() as connection:
                user = connection.execute(
                    'SELECT role, is_active FROM "Users" WHERE user_id = %s',
                    (user_id,),
                ).fetchone()

            if user is None or not user["is_active"]:
                session.clear()
                return jsonify(error="Authentication is required."), 401

            role = user["role"]
            session["role"] = role
            if role not in allowed_roles:
                return jsonify(error="You do not have access to this resource."), 403

            return view(*args, **kwargs)

        return wrapped

    return decorator