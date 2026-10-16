# Requests and Procurement API (Member 4)

Paths have no `/api` prefix, matching the other routes in this repo (`/session`, `/assets`, `/audit`).

**Authentication:** log in with `POST /session/login` and keep the session cookie. Every endpoint below returns `401` if you are not logged in and `403` if your role is not allowed. Errors are JSON: `{"error": "message"}`.

## Requests

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/requests` | admin, manager, store_manager, staff | Raise a request |
| GET | `/requests` | admin, manager, store_manager, staff | List the requests you may see. Filters: `?status=`, `?type=` |
| GET | `/requests/<id>` | admin, manager, store_manager, staff | One request (404 if you may not see it) |
| PATCH | `/requests/<id>/fulfil` | store_manager, admin | Hand an available asset to the requester |

**Who sees what:** staff see their own requests. Managers see their own plus those escalated to them. Store managers see every asset request plus their own. Admins see everything.

### POST /requests

| Field | Required | Notes |
|---|---|---|
| `request_type` | yes | `asset`, `disbursement` or `project` |
| `reason` | yes | Text |
| `item_name` | asset: this or `asset_id` | Up to 150 characters |
| `asset_id` | asset: this or `item_name` | Must exist in Assets |
| `category` | no | Up to 100 characters. Narrows the stock check |
| `quantity` | no | Whole number of 1 or more. Default 1 |
| `amount` | disbursement: yes | Above 0, up to 2 decimal places |
| `project_id` | no | Number |

Response `201`: `{"request": {...}, "procurement": {...} or null}`

What happens next:
- **Asset request, item in stock:** status `pending`, `procurement` is `null`. A store manager fulfils it.
- **Asset request, item not in stock:** a draft procurement is created automatically, the request becomes `converted`, and `procurement` holds the draft.
- **Disbursement or project request:** escalated to the approver with the fewest open requests. Staff and store managers go to a manager, managers and admins go to an admin (never to themselves). With no approver available the status stays `pending`.

### PATCH /requests/<id>/fulfil

Optional body: `{"asset_id": 12}`. Without it, the asset named on the request is used. The asset is marked `assigned` and recorded in Asset_Assignments, and the request becomes `fulfilled`.

Errors: `400` not an asset request or no asset chosen, `404` request or asset not found, `409` request not `pending` or `approved`, or the asset is not available (the response includes `asset_status`).

Request statuses: `pending`, `escalated`, `approved`, `rejected`, `fulfilled`, `converted`, `cancelled`.

## Procurements

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/procurements` | admin, manager, store_manager | List. Filter: `?status=` |
| GET | `/procurements/<id>` | admin, manager, store_manager | One procurement |
| POST | `/procurements` | store_manager, admin | Create a draft, directly or from a request |
| PATCH | `/procurements/<id>` | store_manager, admin | Edit a draft and/or move it along |

### POST /procurements

Fields: `item_name` (required unless `request_id` is given), `category`, `quantity`, `estimated_cost` (0 or more), `supplier`, `reason`, and optional `request_id`.

With `request_id`, the request must be an asset request in `pending` or `approved` status. Missing fields are copied from the request, and the request becomes `converted`. A request can have only one procurement (`409` otherwise). Response `201`: `{"procurement": {...}}`.

### PATCH /procurements/<id>

Send any editable field (drafts only) and/or an `action`:

| Action | From status | To status | Notes |
|---|---|---|---|
| `submit` | draft | pending_approval | Needs `estimated_cost` above 0 |
| `cancel` | draft, pending_approval | cancelled | |
| `purchased` | approved | purchased | |

Errors: `400` nothing to update, bad field or unknown action, `404` not found, `409` editing a non-draft or an action not allowed from the current status.

Procurement statuses: `draft`, `pending_approval`, `approved`, `rejected`, `purchased`, `cancelled`. The `approved` and `rejected` statuses are set by the approvals chain (Member 5).

## Example

    curl -c cookies.txt -X POST http://localhost:5000/session/login \
      -H "Content-Type: application/json" \
      -d '{"identifier": "staff1", "password": "your-password"}'

    curl -b cookies.txt -X POST http://localhost:5000/requests \
      -H "Content-Type: application/json" \
      -d '{"request_type": "asset", "item_name": "Cordless drill", "reason": "Site work"}'
