# Requests and Procurement API (Member 4)

Paths have no `/api` prefix, matching the other routes in this repo (`/session`, `/assets`, `/audit`).

**Authentication:** log in with `POST /session/login` and keep the session cookie. Errors are JSON: `{"error": "message"}` with these codes: `401` not logged in, `403` role not allowed, `404` not found, `409` not allowed in the current state (for example an asset that is already assigned), `422` validation failed.

## Requests

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/requests` | admin, manager, staff | Raise a request |
| GET | `/requests` | admin, manager, staff | List the requests you may see. Filters: `?status=`, `?type=` |
| GET | `/requests/<id>` | admin, manager, staff | One request (404 if you may not see it) |
| PATCH | `/requests/<id>/fulfil` | manager, admin | Hand an available asset to the requester |

**Who sees what:** staff see their own requests. Managers see their own, those escalated to them, and every asset request. Admins see everything.

### POST /requests

| Field | Required | Notes |
|---|---|---|
| `request_type` | yes | `asset`, `disbursement` or `project` |
| `reason` | yes | Text |
| `item_name` | asset: this or `asset_id` | Up to 150 characters |
| `asset_id` | asset: this or `item_name` | Must exist in Assets |
| `asset_type` | no | `tool`, `device` or `vehicle`. Taken from the asset when `asset_id` is given |
| `category` | no | Up to 100 characters. Narrows the stock check |
| `quantity` | no | Whole number of 1 or more. Default 1 |
| `amount` | disbursement: yes | Above 0, up to 2 decimal places |
| `needed_by` | no | Date, `YYYY-MM-DD` |
| `project_id` | no | Number |

Response `201`: `{"request": {...}, "procurement": {...} or null}`

Every request and procurement in a response carries a `history` list, oldest first: `[{"status", "note", "by", "at"}]`. It is the status timeline shown in the app and also serves as an audit trail. A request also shows `requested_by`, `requester_name`, `asset_type` and `needed_by`.

What happens next:
- **Asset request, item in stock:** status `pending`, `procurement` is `null`. A manager fulfils it.
- **Asset request, item not in stock:** a draft procurement is created automatically, the request becomes `converted`, and `procurement` holds the draft.
- **Disbursement or project request:** escalated to the approver with the fewest open requests. Staff go to a manager, managers and admins go to an admin (never to themselves). With no approver available the status stays `pending`.

### PATCH /requests/<id>/fulfil

Optional body: `{"asset_id": 12}`. Without it, the asset named on the request is used. The asset is marked `assigned` and recorded in Asset_Assignments, and the request becomes `fulfilled`.

Errors: `422` not an asset request or no asset chosen, `404` request or asset not found, `409` request not `pending` or `approved`, or the asset is not available (the response includes `asset_status`).

Request statuses: `pending`, `escalated`, `approved`, `rejected`, `fulfilled`, `converted`, `cancelled`.

## Procurements

Procurement is for **managers only**. Other roles get `403`, whatever the page shows.

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/procurements` | manager | List. Filter: `?status=` |
| GET | `/procurements/open` | manager | Procurements that are still unapproved and unpaid |
| GET | `/procurements/<id>` | manager | One procurement |
| POST | `/procurements` | manager | Create a draft, directly or from a request |
| PATCH | `/procurements/<id>` | manager | Edit a draft and/or move it along |

### POST /procurements

The item must exist in the inventory (the `Assets` table). Send `asset_id`, or an `item_name` that matches an inventory item (capitals and surrounding spaces are ignored; the inventory's own spelling is stored). Anything else returns `422`.

Fields: `item_name` or `asset_id` (required unless `request_id` is given), `asset_type`, `category`, `quantity`, `estimated_cost` (0 or more), `supplier`, `reason`, and optional `request_id`.

With `request_id`, the request must be an asset request in `pending` or `approved` status. Missing fields are copied from the request, and the request becomes `converted`. A request can have only one procurement (`409` otherwise). Response `201`: `{"procurement": {...}}`.

### PATCH /procurements/<id>

Send any editable field (drafts only) and/or an `action`:

| Action | From status | To status | Notes |
|---|---|---|---|
| `submit` | draft | pending_approval | Needs `estimated_cost` above 0 |
| `cancel` | draft, pending_approval | cancelled | |
| `purchased` | approved | purchased | |

Errors: `422` nothing to update, bad field, unknown action or an item outside the inventory, `404` not found, `409` editing a non-draft or an action not allowed from the current status.

`GET /procurements/open` returns procurements whose status is `draft`, `pending`, `pending_approval`, `level_1` or `level_2` and that have no paid disbursement.

Procurement statuses: `draft`, `pending`, `pending_approval`, `level_1`, `level_2`, `approved`, `rejected`, `purchased`, `cancelled`. The `approved` and `rejected` statuses are set by the approvals chain (Member 5).

## Example

    curl -c cookies.txt -X POST http://localhost:5000/session/login \
      -H "Content-Type: application/json" \
      -d '{"identifier": "staff1", "password": "your-password"}'

    curl -b cookies.txt -X POST http://localhost:5000/requests \
      -H "Content-Type: application/json" \
      -d '{"request_type": "asset", "item_name": "Cordless drill", "reason": "Site work"}'

## Audit log

Every request and procurement action is written to the audit log with the user, the time and the outcome: `request_created`, `request_fulfilled`, `procurement_created`, `procurement_updated`, `procurement_submitted`, `procurement_cancelled` and `procurement_purchased`.
