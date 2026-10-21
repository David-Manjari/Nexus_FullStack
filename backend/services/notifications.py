"""Helpers for creating in-app notifications inside an existing transaction."""


def create_notification(connection, user_id, message, notif_type="info"):
    """Create one in-app notification for a user."""
    message = message.strip() if isinstance(message, str) else ""
    if not message:
        raise ValueError("A notification message is required.")

    connection.execute(
        'INSERT INTO "Notifications" (user_id, message, notif_type) '
        "VALUES (%s, %s, %s)",
        (user_id, message[:500], notif_type),
    )