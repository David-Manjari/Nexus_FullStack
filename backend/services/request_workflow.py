"""Request workflow: stock check, escalation, procurement conversion and history.

Every function takes an open database connection and runs inside the caller's
transaction, so a request and its follow-up changes are saved or undone together.
"""

REQUESTS = '"Requests"'
ASSETS = '"Assets"'
USERS = '"Users"'
PROCUREMENT = '"Procurement"'
HISTORY = '"Request_History"'

# Who a request is escalated to, by the role of the person who raised it.
# Staff and store managers go to a manager; managers and admins go to an admin.
APPROVER_ROLE = {
    "staff": "manager",
    "store_manager": "manager",
    "manager": "admin",
    "admin": "admin",
}

PROCUREMENT_COLUMNS = (
    "procurement_id, request_id, raised_by, item_name, asset_type, category, "
    "quantity, estimated_cost, supplier, reason, status, created_at, updated_at"
)


# ---------------------------------------------------------------------------
# History (status timeline shown in the app and kept as an audit trail)
# ---------------------------------------------------------------------------
def record_event(connection, entity_type, entity_id, status, note=None, user_id=None):
    """Add one line to a request's or procurement's history.

    entity_type is 'request' or 'procurement'. user_id None means the system.
    """
    connection.execute(
        f"""
        INSERT INTO {HISTORY} (entity_type, entity_id, status, note, changed_by)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (entity_type, entity_id, status, note, user_id),
    )


def attach_history(connection, entity_type, rows, id_key):
    """Add a 'history' list (oldest first) to each row dict, in one query."""
    ids = [row[id_key] for row in rows]
    history = {entity_id: [] for entity_id in ids}
    if ids:
        events = connection.execute(
            f"""
            SELECT h.entity_id, h.status, h.note, h.changed_at,
                   COALESCE(u.username, 'System') AS changed_by_name
            FROM {HISTORY} h
            LEFT JOIN {USERS} u ON u.user_id = h.changed_by
            WHERE h.entity_type = %s AND h.entity_id = ANY(%s)
            ORDER BY h.changed_at, h.history_id
            """,
            (entity_type, ids),
        ).fetchall()
        for event in events:
            history[event["entity_id"]].append({
                "status": event["status"],
                "note": event["note"],
                "by": event["changed_by_name"],
                "at": event["changed_at"],
            })
    for row in rows:
        row["history"] = history[row[id_key]]
    return rows


# ---------------------------------------------------------------------------
# Stock check and escalation
# ---------------------------------------------------------------------------
def check_stock(connection, *, asset_id=None, item_name=None, category=None, quantity=1):
    """Say whether what was asked for is in the store right now.

    A specific asset is available when its status is 'available'. A request by
    name is available when enough available assets contain that name (and match
    the category, if one was given).
    Returns {"available": bool, "asset_id": int | None, "matches": int}.
    """
    if asset_id is not None:
        row = connection.execute(
            f"SELECT status FROM {ASSETS} WHERE asset_id = %s", (asset_id,)
        ).fetchone()
        ok = row is not None and row["status"] == "available"
        return {"available": ok, "asset_id": asset_id if ok else None, "matches": int(ok)}

    if not item_name:
        return {"available": False, "asset_id": None, "matches": 0}

    sql = (
        f"SELECT asset_id FROM {ASSETS} "
        "WHERE status = 'available' AND position(lower(%s) in lower(name)) > 0"
    )
    params = [item_name]
    if category:
        sql += " AND lower(category) = lower(%s)"
        params.append(category)
    rows = connection.execute(sql + " ORDER BY asset_id", params).fetchall()
    ok = len(rows) >= max(quantity, 1)
    return {
        "available": ok,
        "asset_id": rows[0]["asset_id"] if ok else None,
        "matches": len(rows),
    }


def pick_approver(connection, requester_role, requester_id):
    """Pick the approver with the fewest open escalated requests, or None."""
    approver_role = APPROVER_ROLE.get(requester_role, "manager")
    row = connection.execute(
        f"""
        SELECT u.user_id
        FROM {USERS} u
        LEFT JOIN {REQUESTS} r ON r.escalated_to = u.user_id AND r.status = 'escalated'
        WHERE u.role = %s AND u.user_id <> %s
        GROUP BY u.user_id
        ORDER BY COUNT(r.request_id), u.user_id
        LIMIT 1
        """,
        (approver_role, requester_id),
    ).fetchone()
    return row["user_id"] if row else None


def escalate_request(connection, request_id, approver_id):
    """Hand a request to an approver, mark it escalated and log it."""
    connection.execute(
        f"""
        UPDATE {REQUESTS}
        SET status = 'escalated', escalated_to = %s, updated_at = NOW()
        WHERE request_id = %s
        """,
        (approver_id, request_id),
    )
    approver = connection.execute(
        f"SELECT username FROM {USERS} WHERE user_id = %s", (approver_id,)
    ).fetchone()
    record_event(
        connection, "request", request_id, "escalated",
        f"Escalated to {approver['username']}.",
    )


def convert_to_procurement(
    connection, request_id, *, raised_by, actor_id=None,
    request_note="Procurement request created.", **overrides,
):
    """Turn an asset request into a draft procurement and mark it converted.

    Anything in overrides (item_name, asset_type, category, quantity,
    estimated_cost, supplier, reason) replaces the value copied from the
    request. actor_id is who triggered it (None = the system) and is what the
    history shows. Returns the new procurement row.
    """
    req = connection.execute(
        f"""
        SELECT request_id, asset_id, asset_type, item_name, category, quantity, reason
        FROM {REQUESTS} WHERE request_id = %s FOR UPDATE
        """,
        (request_id,),
    ).fetchone()

    item_name = req["item_name"]
    category = req["category"]
    asset_type = req["asset_type"]
    if req["asset_id"] is not None and not (item_name and category and asset_type):
        asset = connection.execute(
            f"SELECT name, category, asset_type FROM {ASSETS} WHERE asset_id = %s",
            (req["asset_id"],),
        ).fetchone()
        if asset:
            item_name = item_name or asset["name"]
            category = category or asset["category"]
            asset_type = asset_type or asset["asset_type"]

    values = {
        "item_name": item_name,
        "asset_type": asset_type,
        "category": category,
        "quantity": req["quantity"],
        "estimated_cost": None,
        "supplier": None,
        "reason": req["reason"],
    }
    values.update({key: value for key, value in overrides.items() if value is not None})

    procurement = connection.execute(
        f"""
        INSERT INTO {PROCUREMENT}
            (request_id, raised_by, item_name, asset_type, category, quantity,
             estimated_cost, supplier, reason)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING {PROCUREMENT_COLUMNS}
        """,
        (request_id, raised_by, values["item_name"], values["asset_type"],
         values["category"], values["quantity"], values["estimated_cost"],
         values["supplier"], values["reason"]),
    ).fetchone()
    connection.execute(
        f"UPDATE {REQUESTS} SET status = 'converted', updated_at = NOW() WHERE request_id = %s",
        (request_id,),
    )
    record_event(
        connection, "procurement", procurement["procurement_id"], "draft",
        f"Created from request {request_id}.", actor_id,
    )
    record_event(connection, "request", request_id, "converted", request_note, actor_id)
    return procurement
