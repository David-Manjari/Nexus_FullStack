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
    build_totp_uri,
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
    qr_code = f"{secrets.randbelow(1_000_000):06d}"
    qr_code_hash = hashlib.sha256(
        f"{challenge_token}:{qr_code}".encode("ascii")
    ).hexdigest()
    with connect_database() as connection:
        connection.execute(
            '''UPDATE "Users"
               SET mfa_pending_expires_at = NOW() + INTERVAL '10 minutes',
                   mfa_challenge_hash = %s, mfa_qr_code_hash = %s,
                   mfa_qr_code_expires_at = NOW() + INTERVAL '5 minutes'
               WHERE user_id = %s''',
            (challenge_hash, qr_code_hash, user["user_id"]),
        )
    response = jsonify(
        mfa_required=True,
        mfa_setup_required=not user["mfa_totp_enabled"],
        totp_available=user["mfa_totp_enabled"],
        qr_code=qr_code,
    )
    response.headers["Cache-Control"] = "no-store"
    return response, 200


def _pending_challenge(connection, user_id, challenge_token):
    user = connection.execute(
        '''SELECT user_id, username, email, role, is_active, mfa_secret,
                  mfa_enabled,
                  mfa_recovery_hashes, mfa_totp_enabled,
                  mfa_failed_attempts, mfa_locked_until > NOW() AS locked,
                  mfa_pending_expires_at > NOW() AS challenge_valid,
                  mfa_qr_code_hash,
                  mfa_qr_code_expires_at > NOW() AS qr_code_valid,
                  mfa_challenge_hash
           FROM "Users" WHERE user_id = %s FOR UPDATE''',
        (user_id,),
    ).fetchone()
    if user is None or not user["is_active"]:
        return None, (jsonify(error="Start a new sign-in to continue."), 401)
    submitted_hash = hashlib.sha256(challenge_token.encode("ascii")).hexdigest()
    if not user["mfa_challenge_hash"] or not hmac.compare_digest(
        submitted_hash, user["mfa_challenge_hash"]
    ):
        return None, (jsonify(error="Start a new sign-in to continue."), 401)
    if user["locked"]:
        return None, (jsonify(error="Too many attempts. Try again later."), 429)
    if not user["challenge_valid"]:
        connection.execute(
            '''UPDATE "Users" SET mfa_pending_expires_at = NULL,
                   mfa_challenge_hash = NULL, mfa_qr_code_hash = NULL,
                   mfa_qr_code_expires_at = NULL
               WHERE user_id = %s''',
            (user_id,),
        )
        session.clear()
        return None, (
            jsonify(error="Your sign-in challenge expired. Please sign in again."),
            401,
        )
    return user, None


@sessions_bp.post("/2fa/totp/setup")
def setup_totp():
    """Generate a TOTP secret during a valid MFA enrollment challenge."""
    user_id = session.get("mfa_pending_user_id")
    challenge_token = session.get("mfa_challenge_token")
    if user_id is None or not isinstance(challenge_token, str):
        return jsonify(error="Start a new sign-in to continue."), 401

    with connect_database() as connection:
        user, error = _pending_challenge(connection, user_id, challenge_token)
        if error:
            return error
        if user["mfa_totp_enabled"]:
            return jsonify(error="An authenticator app is already configured."), 409
        secret = generate_totp_secret()
        connection.execute(
            '''UPDATE "Users" SET mfa_secret = %s
               WHERE user_id = %s''',
            (encrypt_totp_secret(secret), user_id),
        )
        session["mfa_totp_setup_user_id"] = user_id
    return jsonify(
        setup={
            "secret": secret,
            "issuer": "Nexus",
            "otpauth_url": build_totp_uri(secret, user["email"]),
        }
    ), 200


@sessions_bp.post("/2fa/verify")
def verify_two_factor():
    """Complete MFA enrollment or a login challenge using TOTP or recovery."""
    data = request.get_json(silent=True)
    code = data.get("code") if isinstance(data, dict) else None
    method = data.get("method", "totp") if isinstance(data, dict) else "totp"
    user_id = session.get("mfa_pending_user_id")
    challenge_token = session.get("mfa_challenge_token")
    if user_id is None or not isinstance(challenge_token, str):
        return jsonify(error="Start a new sign-in to continue."), 401
    if method not in ("qr", "totp", "recovery"):
        return jsonify(error="Choose a supported verification method."), 400
    if not isinstance(code, str) or not code.strip() or len(code) > 64:
        return jsonify(error="Enter your verification code."), 400

    recovery_codes = None
    with connect_database() as connection:
        user, error = _pending_challenge(connection, user_id, challenge_token)
        if error:
            return error
        hashes = user.get("mfa_recovery_hashes", [])
        recovery_index = None
        valid_code = False
        if method == "totp":
            setup_in_progress = session.get("mfa_totp_setup_user_id") == user_id
            if not user.get("mfa_secret") or (
                not user["mfa_totp_enabled"] and not setup_in_progress
            ):
                return jsonify(error="An authenticator app is not configured."), 409
            secret = decrypt_totp_secret(user["mfa_secret"])
            valid_code = verify_totp(secret, code.strip())
            if not valid_code and user["mfa_enabled"]:
                recovery_index = consume_recovery_code(code, hashes)
                if recovery_index is not None:
                    method = "recovery"
                    valid_code = True
        elif method == "qr":
            if not user["mfa_qr_code_hash"] or not user["qr_code_valid"]:
                return jsonify(error="Request a new sign-in QR code first."), 409
            submitted_qr_hash = hashlib.sha256(
                f"{challenge_token}:{code.strip()}".encode("ascii")
            ).hexdigest()
            valid_code = hmac.compare_digest(
                submitted_qr_hash, user["mfa_qr_code_hash"]
            )
        else:
            recovery_index = consume_recovery_code(code, hashes)
            valid_code = recovery_index is not None

        if not valid_code:
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
            return jsonify(error="The verification code is invalid."), 401

        first_factor = not hashes and not user["mfa_totp_enabled"]
        if first_factor:
            recovery_codes, hashes = generate_recovery_codes()
        if method == "totp":
            connection.execute(
                '''UPDATE "Users"
                   SET mfa_enabled = TRUE, mfa_totp_enabled = TRUE,
                       mfa_recovery_hashes = %s,
                       mfa_failed_attempts = 0, mfa_locked_until = NULL,
                       mfa_pending_expires_at = NULL, mfa_challenge_hash = NULL,
                       mfa_qr_code_hash = NULL, mfa_qr_code_expires_at = NULL
                   WHERE user_id = %s''',
                (Jsonb(hashes), user_id),
            )
        elif method == "qr":
            connection.execute(
                '''UPDATE "Users"
                   SET mfa_enabled = TRUE, mfa_recovery_hashes = %s,
                       mfa_failed_attempts = 0, mfa_locked_until = NULL,
                       mfa_pending_expires_at = NULL, mfa_challenge_hash = NULL,
                       mfa_qr_code_hash = NULL, mfa_qr_code_expires_at = NULL
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
                       mfa_challenge_hash = NULL, mfa_qr_code_hash = NULL,
                       mfa_qr_code_expires_at = NULL
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
