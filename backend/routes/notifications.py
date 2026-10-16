"""Session-scoped notification listing and read-state routes."""

from flask import Blueprint, jsonify, session

from ..auth import roles_required
from ..db import connect_database


notifications_bp = Blueprint("notifications", __name__)
READ_ROLES = ("admin", "manager", "store_manager", "staff")


@notifications_bp.get("")
@roles_required(*READ_ROLES)
def list_notifications():
	with connect_database() as connection:
		notifications = connection.execute(
			'''SELECT notification_id, user_id, message, notif_type, is_read,
					  email_sent, created_at
			   FROM "Notifications" WHERE user_id = %s
			   ORDER BY created_at DESC, notification_id DESC LIMIT 100''',
			(session["user_id"],),
		).fetchall()
	return jsonify(notifications=notifications), 200


@notifications_bp.patch("/<int:notification_id>/read")
@roles_required(*READ_ROLES)
def mark_notification_read(notification_id):
	with connect_database() as connection:
		notification = connection.execute(
			'''UPDATE "Notifications" SET is_read = TRUE
			   WHERE notification_id = %s AND user_id = %s
			   RETURNING notification_id, user_id, message, notif_type, is_read,
						 email_sent, created_at''',
			(notification_id, session["user_id"]),
		).fetchone()
	if notification is None:
		return jsonify(error="Notification not found."), 404
	return jsonify(notification=notification), 200


@notifications_bp.post("/read-all")
@roles_required(*READ_ROLES)
def mark_all_notifications_read():
	with connect_database() as connection:
		connection.execute(
			'''UPDATE "Notifications" SET is_read = TRUE
			   WHERE user_id = %s AND is_read = FALSE''',
			(session["user_id"],),
		)
	return jsonify(message="Notifications marked as read."), 200
