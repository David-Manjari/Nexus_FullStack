"""Session-based login and logout routes.

Register ``sessions_bp`` with the Flask application and configure its secret key
from a secure environment variable before serving requests.
"""

import hashlib
import hmac
import secrets

from flask import Blueprint, jsonify, request, session
from psycopg.types.json import Jsonb

from ..db import connect_database
from ..mfa import (
    consume_recovery_code,
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_recovery_codes,
    generate_totp_secret,
    verify_totp,
)
from ..user_login import AuthenticationError, authenticate_user


sessions_bp = Blueprint("sessions", __name__)


@sessions_bp.post("/login")
def login():
    """Authenticate a user and persist their identity in the Flask session."""
    data = request.get_json(silent=True) if request.is_json else request.form
    if not hasattr(data, "get"):
        data = {}
    identifier = data.get("identifier") or data.get("username") or data.get("email")
    password = data.get("password")

    if not isinstance(identifier, str) or not identifier.strip():
        return jsonify(error="Username or email is required."), 400
    if not isinstance(password, str) or not password:
        return jsonify(error="Password is required."), 400

    try:
        user = authenticate_user(identifier, password)
    except AuthenticationError as error:
        return jsonify(error=str(error)), error.status_code

    session.clear()
    session.permanent = True
    session["mfa_pending_user_id"] = user["user_id"]
    challenge_token = secrets.token_urlsafe(32)
    session["mfa_challenge_token"] = challenge_token
    challenge_hash = hashlib.sha256(challenge_token.encode("ascii")).hexdigest()
    with connect_database() as connection:
        if user["mfa_enabled"]:
            connection.execute(
                '''UPDATE "Users"
                   SET mfa_pending_expires_at = NOW() + INTERVAL '10 minutes',
                       mfa_challenge_hash = %s
                   WHERE user_id = %s''',
                (challenge_hash, user["user_id"]),
            )
            return jsonify(mfa_required=True, mfa_setup_required=False), 200

        secret = generate_totp_secret()
        connection.execute(
            '''UPDATE "Users"
               SET mfa_secret = %s, mfa_recovery_hashes = '[]'::jsonb,
                   mfa_failed_attempts = 0, mfa_locked_until = NULL,
                   mfa_pending_expires_at = NOW() + INTERVAL '10 minutes',
                   mfa_challenge_hash = %s
               WHERE user_id = %s AND mfa_enabled = FALSE''',
            (encrypt_totp_secret(secret), challenge_hash, user["user_id"]),
        )
    return jsonify(
        mfa_required=True,
        mfa_setup_required=True,
        setup={
            "secret": secret,
            "account": user["email"],
            "issuer": "Nexus",
        },
    ), 200


@sessions_bp.post("/2fa/verify")
def verify_two_factor():
    """Complete MFA enrollment or a login challenge using TOTP or a recovery code."""
    data = request.get_json(silent=True)
    code = data.get("code") if isinstance(data, dict) else None
    user_id = session.get("mfa_pending_user_id")
    challenge_token = session.get("mfa_challenge_token")
    if user_id is None or not isinstance(challenge_token, str):
        return jsonify(error="Start a new sign-in to continue."), 401
    if not isinstance(code, str) or not code.strip() or len(code) > 64:
        return jsonify(error="Enter your authenticator or recovery code."), 400

    recovery_codes = None
    with connect_database() as connection:
        user = connection.execute(
            '''SELECT user_id, username, email, role, is_active, mfa_secret,
                      mfa_enabled, mfa_recovery_hashes, mfa_failed_attempts,
                      mfa_locked_until, mfa_locked_until > NOW() AS locked,
                      mfa_pending_expires_at,
                      mfa_pending_expires_at > NOW() AS challenge_valid,
                      mfa_challenge_hash
               FROM "Users" WHERE user_id = %s FOR UPDATE''',
            (user_id,),
        ).fetchone()
        if user is None or not user["is_active"]:
            session.clear()
            return jsonify(error="Start a new sign-in to continue."), 401
        submitted_challenge_hash = hashlib.sha256(challenge_token.encode("ascii")).hexdigest()
        if not user["mfa_challenge_hash"] or not hmac.compare_digest(
            submitted_challenge_hash, user["mfa_challenge_hash"]
        ):
            session.clear()
            return jsonify(error="Start a new sign-in to continue."), 401
        if user["locked"]:
            return jsonify(error="Too many attempts. Try again later."), 429
        if not user["challenge_valid"]:
            connection.execute(
                '''UPDATE "Users" SET mfa_pending_expires_at = NULL,
                       mfa_challenge_hash = NULL WHERE user_id = %s''',
                (user_id,),
            )
            session.clear()
            return jsonify(error="Your sign-in challenge expired. Please sign in again."), 401
        if not user["mfa_secret"]:
            return jsonify(error="Two-factor setup is unavailable. Please sign in again."), 409

        secret = decrypt_totp_secret(user["mfa_secret"])
        valid_totp = verify_totp(secret, code.strip())
        recovery_index = None
        hashes = user["mfa_recovery_hashes"]
        if not valid_totp and user["mfa_enabled"]:
            recovery_index = consume_recovery_code(code, hashes)
        if not valid_totp and recovery_index is None:
            attempts = user["mfa_failed_attempts"] + 1
            connection.execute(
                '''UPDATE "Users"
                   SET mfa_failed_attempts = %s,
                       mfa_locked_until = CASE WHEN %s >= 5
                           THEN NOW() + INTERVAL '10 minutes' ELSE mfa_locked_until END
                   WHERE user_id = %s''',
                (attempts, attempts, user_id),
            )
            if attempts >= 5:
                return jsonify(error="Too many attempts. Try again later."), 429
            return jsonify(error="The authenticator or recovery code is invalid."), 401

        if not user["mfa_enabled"]:
            recovery_codes, hashes = generate_recovery_codes()
            connection.execute(
                '''UPDATE "Users"
                   SET mfa_enabled = TRUE, mfa_recovery_hashes = %s,
                       mfa_failed_attempts = 0, mfa_locked_until = NULL,
                       mfa_pending_expires_at = NULL, mfa_challenge_hash = NULL
                   WHERE user_id = %s''',
                (Jsonb(hashes), user_id),
            )
        else:
            if recovery_index is not None:
                hashes = [value for index, value in enumerate(hashes) if index != recovery_index]
            connection.execute(
                '''UPDATE "Users"
                   SET mfa_recovery_hashes = %s, mfa_failed_attempts = 0,
                       mfa_locked_until = NULL, mfa_pending_expires_at = NULL,
                       mfa_challenge_hash = NULL
                   WHERE user_id = %s''',
                (Jsonb(hashes), user_id),
            )

    session.clear()
    session.permanent = True
    session["user_id"] = user["user_id"]
    session["username"] = user["username"]
    session["role"] = user["role"]
    session["mfa_verified"] = True
    result = {
        "user": {
            "user_id": user["user_id"],
            "username": user["username"],
            "email": user["email"],
            "role": user["role"],
        }
    }
    if recovery_codes is not None:
        result["recovery_codes"] = recovery_codes
    return jsonify(**result), 200


@sessions_bp.get("/me")
def current_session():
    """Return the current active user so browser clients can restore a session."""
    user_id = session.get("user_id")
    if user_id is None or session.get("mfa_verified") is not True:
        session.clear()
        return jsonify(error="Authentication is required."), 401

    with connect_database() as connection:
        user = connection.execute(
            '''SELECT user_id, username, email, role, is_active
               FROM "Users" WHERE user_id = %s''',
            (user_id,),
        ).fetchone()

    if user is None or not user["is_active"]:
        session.clear()
        return jsonify(error="Authentication is required."), 401

    safe_user = {key: user[key] for key in ("user_id", "username", "email", "role")}
    return jsonify(user=safe_user), 200


@sessions_bp.post("/logout")
def logout():
    """Clear the current user's session."""
    session.clear()
    return jsonify(message="Logged out successfully."), 200
