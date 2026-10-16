"""Asset inventory routes (tools, devices, vehicles).

Store Managers create, edit, assign and receive back assets.
Every other signed-in role can read.

Register both blueprints in app.py:
    app.register_blueprint(assets_bp, url_prefix="/assets")
    app.register_blueprint(assignments_bp, url_prefix="/assignments")
"""

import os
import uuid
from datetime import date

from flask import Blueprint, jsonify, request, send_from_directory, session
from psycopg.types.json import Jsonb
from werkzeug.utils import secure_filename

from ..db import connect_database
from ..auth import roles_required

assets_bp = Blueprint("assets", __name__)
assignments_bp = Blueprint("assignments", __name__)

# ---------------------------------------------------------------------------
# Table names match schema.sql. Roles come from ROLES in admin_accounts.py.
# ---------------------------------------------------------------------------
ASSETS = '"Assets"'
VEHICLES = '"Vehicle_Details"'
ASSIGNMENTS = '"Asset_Assignments"'
USERS = '"Users"'

WRITE_ROLES = ("store_manager",)
READ_ROLES = ("admin", "manager", "store_manager", "staff")

ASSET_TYPES = {"tool", "device", "vehicle"}
EDITABLE_STATUSES = {"available", "maintenance", "retired"}  # "assigned" only via /assign
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
MAX_IMAGE_BYTES = 2 * 1024 * 1024
UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads", "assets"
)

ASSET_SELECT = f"""
SELECT a.asset_id, a.asset_type, a.name, a.category, a.brand, a.serial_no,
       a.condition, a.status, a.image_path, a.added_by, a.created_at,
    v.plate_no, v.make, v.model, v.mileage,
    current_assignment.assignment_id AS current_assignment_id,
    current_assignment.user_id AS assigned_to_user_id,
    assigned_user.username AS assigned_to_username
FROM {ASSETS} a
LEFT JOIN {VEHICLES} v ON v.asset_id = a.asset_id
LEFT JOIN {ASSIGNMENTS} current_assignment
    ON current_assignment.asset_id = a.asset_id AND current_assignment.returned_at IS NULL
LEFT JOIN {USERS} assigned_user ON assigned_user.user_id = current_assignment.user_id
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _error(message, status):
    return jsonify(error=message), status


def _payload():
    """Read JSON or form fields (forms are used when an image is uploaded)."""
    if request.is_json:
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}
    return request.form.to_dict()


def _text(data, key):
    value = data.get(key)
    if isinstance(value, str):
        return value.strip() or None
    return None


def _int(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number


def _is_unique_violation(error):
    code = getattr(error, "sqlstate", None) or getattr(error, "pgcode", None)
    return code == "23505"


def _present(row):
    asset = dict(row)
    path = asset.get("image_path")
    asset["image_url"] = f"/assets/images/{path}" if path else None
    return asset


def _save_image(file):
    """Validate and store an uploaded image. Returns (filename, error)."""
    extension = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        return None, "Image must be a PNG, JPG or WEBP file."

    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size == 0 or size > MAX_IMAGE_BYTES:
        return None, "Image must be between 1 byte and 2 MB."

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    filename = secure_filename(f"{uuid.uuid4().hex}.{extension}")
    file.save(os.path.join(UPLOAD_DIR, filename))
    return filename, None


def _audit(connection, action, asset_id, details=None):
    """Write one row to the shared Audit_Log table, inside the caller's transaction."""
    connection.execute(
        'INSERT INTO "Audit_Log" (user_id, action, entity_type, entity_id, details) '
        "VALUES (%s, %s, 'asset', %s, %s)",
        (session["user_id"], action, asset_id, Jsonb(details or {})),
    )


def _notify(connection, user_id, message, notif_type="asset_assigned"):
    """Insert an in-app notification. Swap for services.notifications once it exists."""
    connection.execute(
        'INSERT INTO "Notifications" (user_id, message, notif_type) VALUES (%s, %s, %s)',
        (user_id, message, notif_type),
    )


def _remove_image(filename):
    if filename:
        try:
            os.remove(os.path.join(UPLOAD_DIR, filename))
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------
@assets_bp.get("")
@roles_required(*READ_ROLES)
def list_assets():
    """List assets. Filters: ?type=&status=&category=&q=search"""
    clauses, params = [], []
    for arg, column in (("type", "a.asset_type"), ("status", "a.status"), ("category", "a.category")):
        value = request.args.get(arg, "").strip()
        if value:
            clauses.append(f"{column} = %s")
            params.append(value)

    search = request.args.get("q", "").strip()
    if search:
        clauses.append("(a.name ILIKE %s OR a.serial_no ILIKE %s OR a.brand ILIKE %s)")
        params.extend([f"%{search}%"] * 3)

    query = ASSET_SELECT
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY a.created_at DESC, a.asset_id DESC"

    with connect_database() as connection:
        rows = connection.execute(query, params).fetchall()
    return jsonify(assets=[_present(row) for row in rows]), 200


@assets_bp.get("/<int:asset_id>")
@roles_required(*READ_ROLES)
def get_asset(asset_id):
    with connect_database() as connection:
        row = connection.execute(
            ASSET_SELECT + " WHERE a.asset_id = %s", (asset_id,)
        ).fetchone()
    if row is None:
        return _error("Asset not found.", 404)
    return jsonify(asset=_present(row)), 200


@assets_bp.post("")
@roles_required(*WRITE_ROLES)
def create_asset():
    data = _payload()
    asset_type = (_text(data, "asset_type") or "").lower()
    name = _text(data, "name")
    if asset_type not in ASSET_TYPES:
        return _error("asset_type must be tool, device or vehicle.", 400)
    if not name:
        return _error("name is required.", 400)

    vehicle = None
    if asset_type == "vehicle":
        plate_no = _text(data, "plate_no")
        mileage = _int(data.get("mileage", 0))
        if not plate_no:
            return _error("plate_no is required for vehicles.", 400)
        if mileage is None or mileage < 0:
            return _error("mileage must be a number of 0 or more.", 400)
        vehicle = (plate_no, _text(data, "make"), _text(data, "model"), mileage)

    image_name = None
    upload = request.files.get("image")
    if upload and upload.filename:
        image_name, problem = _save_image(upload)
        if problem:
            return _error(problem, 400)

    try:
        with connect_database() as connection:
            asset_id = connection.execute(
                f"""INSERT INTO {ASSETS}
                    (asset_type, name, category, brand, serial_no, condition,
                     status, image_path, added_by)
                    VALUES (%s, %s, %s, %s, %s, %s, 'available', %s, %s)
                    RETURNING asset_id""",
                (
                    asset_type, name, _text(data, "category"), _text(data, "brand"),
                    _text(data, "serial_no"), _text(data, "condition") or "good",
                    image_name, session["user_id"],
                ),
            ).fetchone()["asset_id"]

            if vehicle:
                connection.execute(
                    f"""INSERT INTO {VEHICLES} (asset_id, plate_no, make, model, mileage)
                        VALUES (%s, %s, %s, %s, %s)""",
                    (asset_id, *vehicle),
                )
            _audit(connection, "asset_created", asset_id, {"name": name, "asset_type": asset_type})
            row = connection.execute(
                ASSET_SELECT + " WHERE a.asset_id = %s", (asset_id,)
            ).fetchone()
    except Exception as error:
        _remove_image(image_name)
        if _is_unique_violation(error):
            return _error("An asset with that serial number or plate already exists.", 409)
        raise

    return jsonify(asset=_present(row)), 201


@assets_bp.patch("/<int:asset_id>")
@roles_required(*WRITE_ROLES)
def update_asset(asset_id):
    data = _payload()
    asset_fields = {}
    for key in ("name", "category", "brand", "serial_no", "condition"):
        if key in data:
            value = _text(data, key)
            if key == "name" and not value:
                return _error("name cannot be empty.", 400)
            asset_fields[key] = value

    vehicle_fields = {}
    for key in ("plate_no", "make", "model"):
        if key in data:
            vehicle_fields[key] = _text(data, key)
    if "mileage" in data:
        mileage = _int(data.get("mileage"))
        if mileage is None or mileage < 0:
            return _error("mileage must be a number of 0 or more.", 400)
        vehicle_fields["mileage"] = mileage

    new_status = None
    if "status" in data:
        new_status = _text(data, "status")
        if new_status not in EDITABLE_STATUSES:
            return _error("status must be available, maintenance or retired.", 400)

    image_name = None
    upload = request.files.get("image")
    if upload and upload.filename:
        image_name, problem = _save_image(upload)
        if problem:
            return _error(problem, 400)
        asset_fields["image_path"] = image_name

    if new_status:
        asset_fields["status"] = new_status
    if not asset_fields and not vehicle_fields:
        return _error("No valid fields to update.", 400)

    old_image = None
    try:
        with connect_database() as connection:
            current = connection.execute(
                f"SELECT asset_type, status, image_path FROM {ASSETS} WHERE asset_id = %s FOR UPDATE",
                (asset_id,),
            ).fetchone()
            if current is None:
                _remove_image(image_name)
                return _error("Asset not found.", 404)
            if new_status and current["status"] == "assigned":
                _remove_image(image_name)
                return _error("Return the asset before changing its status.", 409)
            if vehicle_fields and current["asset_type"] != "vehicle":
                _remove_image(image_name)
                return _error("Only vehicles have plate, make, model or mileage.", 400)

            if asset_fields:
                sets = ", ".join(f"{column} = %s" for column in asset_fields)
                connection.execute(
                    f"UPDATE {ASSETS} SET {sets} WHERE asset_id = %s",
                    (*asset_fields.values(), asset_id),
                )
            if vehicle_fields:
                sets = ", ".join(f"{column} = %s" for column in vehicle_fields)
                connection.execute(
                    f"UPDATE {VEHICLES} SET {sets} WHERE asset_id = %s",
                    (*vehicle_fields.values(), asset_id),
                )
            if image_name:
                old_image = current["image_path"]
            _audit(
                connection, "asset_updated", asset_id,
                {"fields": sorted([*asset_fields, *vehicle_fields])},
            )
            row = connection.execute(
                ASSET_SELECT + " WHERE a.asset_id = %s", (asset_id,)
            ).fetchone()
    except Exception as error:
        _remove_image(image_name)
        if _is_unique_violation(error):
            return _error("An asset with that serial number or plate already exists.", 409)
        raise

    _remove_image(old_image)
    return jsonify(asset=_present(row)), 200


@assets_bp.get("/<int:asset_id>/history")
@roles_required(*READ_ROLES)
def asset_history(asset_id):
    """Full lending history for one asset, newest first."""
    with connect_database() as connection:
        exists = connection.execute(
            f"SELECT 1 AS found FROM {ASSETS} WHERE asset_id = %s", (asset_id,)
        ).fetchone()
        if exists is None:
            return _error("Asset not found.", 404)
        rows = connection.execute(
            f"""SELECT s.assignment_id, s.user_id, u.username AS assigned_to,
                       s.project_id, s.request_id, s.assigned_by,
                       b.username AS assigned_by_name, s.assigned_at,
                       s.due_back, s.returned_at, s.return_condition
                FROM {ASSIGNMENTS} s
                JOIN {USERS} u ON u.user_id = s.user_id
                LEFT JOIN {USERS} b ON b.user_id = s.assigned_by
                WHERE s.asset_id = %s
                ORDER BY s.assigned_at DESC, s.assignment_id DESC""",
            (asset_id,),
        ).fetchall()
    return jsonify(history=[dict(row) for row in rows]), 200


@assets_bp.post("/<int:asset_id>/assign")
@roles_required(*WRITE_ROLES)
def assign_asset(asset_id):
    data = _payload()
    user_id = _int(data.get("user_id"))
    if user_id is None:
        return _error("user_id is required.", 400)

    project_id = _int(data["project_id"]) if data.get("project_id") not in (None, "") else None
    request_id = _int(data["request_id"]) if data.get("request_id") not in (None, "") else None
    if data.get("project_id") not in (None, "") and project_id is None:
        return _error("project_id must be a number.", 400)
    if data.get("request_id") not in (None, "") and request_id is None:
        return _error("request_id must be a number.", 400)

    due_back = _text(data, "due_back")
    if due_back:
        try:
            date.fromisoformat(due_back)
        except ValueError:
            return _error("due_back must be a date like 2026-10-31.", 400)

    with connect_database() as connection:
        asset = connection.execute(
            f"SELECT name, status FROM {ASSETS} WHERE asset_id = %s FOR UPDATE", (asset_id,)
        ).fetchone()
        if asset is None:
            return _error("Asset not found.", 404)
        if asset["status"] != "available":
            return _error(f"Asset is {asset['status']}, not available.", 409)

        user = connection.execute(
            f"SELECT user_id FROM {USERS} WHERE user_id = %s", (user_id,)
        ).fetchone()
        if user is None:
            return _error("That user does not exist.", 404)

        assignment_id = connection.execute(
            f"""INSERT INTO {ASSIGNMENTS}
                (asset_id, user_id, project_id, request_id, assigned_by, due_back)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING assignment_id""",
            (asset_id, user_id, project_id, request_id, session["user_id"], due_back),
        ).fetchone()["assignment_id"]
        connection.execute(
            f"UPDATE {ASSETS} SET status = 'assigned' WHERE asset_id = %s", (asset_id,)
        )
        _audit(
            connection, "asset_assigned", asset_id,
            {"assigned_to": user_id, "assignment_id": assignment_id, "request_id": request_id},
        )
        _notify(connection, user_id, f"You were assigned: {asset['name']}.")

    return jsonify(message="Asset assigned.", assignment_id=assignment_id), 201


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------
@assets_bp.get("/images/<path:filename>")
@roles_required(*READ_ROLES)
def asset_image(filename):
    return send_from_directory(UPLOAD_DIR, filename)


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------
@assignments_bp.post("/<int:assignment_id>/return")
@roles_required(*WRITE_ROLES)
def return_asset(assignment_id):
    """Mark an assignment as returned. Optional: return_condition, send_to_maintenance."""
    data = _payload()
    return_condition = _text(data, "return_condition")
    to_maintenance = str(data.get("send_to_maintenance", "")).lower() in ("true", "1", "yes")

    with connect_database() as connection:
        assignment = connection.execute(
            f"SELECT asset_id, returned_at FROM {ASSIGNMENTS} WHERE assignment_id = %s FOR UPDATE",
            (assignment_id,),
        ).fetchone()
        if assignment is None:
            return _error("Assignment not found.", 404)
        if assignment["returned_at"] is not None:
            return _error("This asset was already returned.", 409)

        connection.execute(
            f"""UPDATE {ASSIGNMENTS}
                SET returned_at = NOW(), return_condition = %s
                WHERE assignment_id = %s""",
            (return_condition, assignment_id),
        )
        connection.execute(
            f"""UPDATE {ASSETS}
                SET status = %s, condition = COALESCE(%s, condition)
                WHERE asset_id = %s""",
            ("maintenance" if to_maintenance else "available", return_condition, assignment["asset_id"]),
        )
        _audit(
            connection, "asset_returned", assignment["asset_id"],
            {"assignment_id": assignment_id, "return_condition": return_condition,
             "to_maintenance": to_maintenance},
        )

    return jsonify(message="Asset returned."), 200