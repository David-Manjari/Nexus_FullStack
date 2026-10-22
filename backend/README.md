# Nexus Backend

Nexus is a role-aware operations API for organizations coordinating inventory, field requests, procurement, approvals, projects, and disbursements. It provides a shared PostgreSQL data store and HTTP endpoints for workflows that might otherwise rely on paper forms, spreadsheets, and chat.

**Project status:** This repository contains the Phase 2 database and Flask backend. It includes local demo accounts and sample data. Disbursements can be sent through the Safaricom Daraja B2C sandbox when explicitly enabled; the integration is pinned to the sandbox and cannot send production payouts.

## Backend capabilities

- Session-based login and logout with role-aware, protected endpoints.
- PostgreSQL-backed user accounts, assets, projects, requests, procurement, approvals, disbursements, and audit data.
- Asset inventory endpoints for listing, creating, editing, assignment, returns, and assignment history.
- Request creation and status tracking, including automatic draft procurement creation when an asset is unavailable.
- Procurement draft creation and updates, with approval workflow endpoints.
- Project creation, tracking, submission, and status updates.
- Admin account listing, creation, editing, password changes, and deactivation. Passwords are stored as hashes; at least one active admin must remain.
- Disbursement records, approved sandbox payout submission, callback-driven status, payment history, and audit history.
- JSON error responses for common validation, authorization, missing-record, conflict, and database errors.

List endpoints return empty JSON collections when there are no matching records. Protected routes return `401` when authentication is missing and `403` when the signed-in role is not allowed. Other common responses include `400` for invalid input, `404` for missing or inaccessible records, `409` for conflicts, and `503` when the database is unavailable.

## API routes

The disbursement blueprint uses the `/api` prefix. Other routes do not. Route-level role checks apply as configured by the backend.

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | API status |
| GET | `/health` | Health check |
| POST | `/session/login` | Start a session |
| POST | `/session/logout` | End a session |
| GET | `/users/accounts` | List accounts (admin) |
| GET | `/users/accounts/<int:user_id>` | Get an account (admin) |
| POST | `/users/accounts` | Create an account (admin) |
| PATCH | `/users/accounts/<int:user_id>` | Update account fields, role, password, or active state (admin) |
| DELETE | `/users/accounts/<int:user_id>` | Deactivate an account (admin) |
| GET | `/users/accounts/activity` | Get account activity (admin) |
| GET | `/approvals/inbox` | List the current approver's inbox |
| POST | `/approvals/<int:approval_id>/decision` | Approve or reject an approval |
| GET | `/audit/company` | Company audit summary |
| GET | `/audit/company/projects` | Project audit summary |
| GET | `/audit/company/disbursements` | Disbursement audit summary |
| GET | `/audit/company/procurement` | Procurement audit summary |
| GET | `/assets` | List assets |
| GET | `/assets/<int:asset_id>` | Get an asset |
| POST | `/assets` | Create an asset |
| PATCH | `/assets/<int:asset_id>` | Update an asset |
| GET | `/assets/<int:asset_id>/history` | Get asset assignment history |
| POST | `/assets/<int:asset_id>/assign` | Assign an asset |
| GET | `/assets/images/<path:filename>` | Retrieve an asset image |
| POST | `/assignments/<int:assignment_id>/return` | Record an asset return |
| GET | `/requests` | List visible requests; supports `status` and `type` filters |
| POST | `/requests` | Create a request |
| GET | `/requests/<int:request_id>` | Get a visible request |
| PATCH | `/requests/<int:request_id>/fulfil` | Fulfil an asset request |
| GET | `/procurements` | List procurements; supports a `status` filter |
| GET | `/procurements/<int:procurement_id>` | Get a procurement |
| POST | `/procurements` | Create a procurement draft |
| PATCH | `/procurements/<int:procurement_id>` | Update a draft or advance its workflow |
| GET | `/projects` | List visible projects |
| POST | `/projects` | Create a project |
| GET | `/projects/<int:project_id>` | Get a project |
| PATCH | `/projects/<int:project_id>` | Update a project |
| GET | `/projects/assignable-users` | List active project managers and staff (admin/manager) |
| GET | `/projects/approvers` | List active managers and admins eligible to approve projects, excluding the current user |
| PATCH | `/projects/<int:project_id>/team` | Assign the project manager and/or staff (admin/manager) |
| POST | `/projects/<int:project_id>/submit` | Submit a project for approval |
| PATCH | `/projects/<int:project_id>/status` | Update project status |
| POST | `/projects/<int:project_id>/milestones` | Add a project milestone (admin, manager, or assigned project manager) |
| PATCH | `/projects/<int:project_id>/milestones/<int:milestone_id>` | Update milestone progress (admin, manager, or assigned project manager) |
| GET | `/api/disbursements` | List disbursements; supports a `status` filter |
| GET | `/api/disbursements/summary` | Get disbursement totals by status |
| POST | `/api/disbursements` | Create a disbursement |
| GET | `/api/disbursements/<int:disbursement_id>` | Get a disbursement |
| POST | `/api/disbursements/<int:disbursement_id>/process` | Submit an approved payout to Daraja B2C sandbox |
| POST | `/api/daraja/b2c/result/<token>` | Receive a Daraja result callback |
| POST | `/api/daraja/b2c/timeout/<token>` | Receive a Daraja timeout callback |
| GET | `/api/disbursements/<int:disbursement_id>/history` | Get payment and audit history |
| GET | `/api/payment-history` | List payment history |

For request and procurement payload details and workflow behavior, see [docs/api-requests-procurement.md](docs/api-requests-procurement.md).

## Request body keys

Send JSON unless uploading an asset image, which uses `multipart/form-data`. Required fields and conditional requirements are noted below; other listed keys are optional.

New account passwords and password changes must contain at least 8 characters, including an uppercase letter, a lowercase letter, a number, and a special character. Signing in does not revalidate this policy, so existing accounts remain able to log in and can adopt the policy when their password is changed.

## Daraja B2C sandbox setup

The integration is disabled by default. Start from the root `.env.example` and set the following in the untracked root `.env` only after creating a Daraja sandbox app:

- `DARAJA_B2C_ENABLED=true`
- `DARAJA_CONSUMER_KEY` and `DARAJA_CONSUMER_SECRET` from the sandbox app
- `DARAJA_INITIATOR_NAME`, `DARAJA_SHORTCODE`, and `DARAJA_SECURITY_CREDENTIAL` from the sandbox setup
- `DARAJA_B2C_COMMAND_ID` to a command enabled for the use case (`BusinessPayment` by default)
- `DARAJA_CALLBACK_BASE_URL` to a public HTTPS URL that routes to this backend
- `DARAJA_CALLBACK_TOKEN` to a locally generated random value of at least 32 characters

Configure the same callback base URL and token in the Daraja request callback URLs. For local development, use an HTTPS tunnel to the backend; do not expose the frontend or use plain HTTP. Generate the security credential using Safaricom's sandbox certificate and instructions; do not store the initiator password or credentials in source control.

Payout creation accepts Kenyan mobile numbers and whole KES amounts from 1 through 70,000. A separate admin/manager must approve the payout, and the approver cannot submit it. Submission moves the item to `processing`; only a correlated Daraja callback with a matching amount and transaction receipt marks it paid. A timeout or ambiguous network response remains `processing` and must be reconciled before anyone retries. Do not assume a successful submission response means the payout completed. The callback token is an additional shared-secret guard, not a Daraja callback signature; callback transaction IDs and amount are also checked.

The B2C client uses only `https://sandbox.safaricom.co.ke`. Sandbox test values and behavior are controlled by Safaricom and may differ from production. No live-money credentials or production endpoint should be added to this integration.

| Method and path | Body keys |
|---|---|
| `POST /session/login` | `identifier` or `username` or `email`, and `password` (required; JSON or form data) |
| `POST /users/accounts` | `username`, `email`, `password`, `role` (all required) |
| `PATCH /users/accounts/<int:user_id>` | `username`, `email`, `password`, `role`, `is_active` (at least one required) |
| `POST /approvals/<int:approval_id>/decision` | `decision` (required: `approved` or `rejected`), `comments` |
| `POST /assets` | `asset_type`, `name` (required); `category`, `brand`, `serial_no`, `condition`, `image`; vehicles also accept required `plate_no`, plus `make`, `model`, `mileage` (defaults to `0`) |
| `PATCH /assets/<int:asset_id>` | `name`, `category`, `brand`, `serial_no`, `condition`, `status`, `image`, `plate_no`, `make`, `model`, `mileage` (at least one field; vehicle fields only apply to vehicles) |
| `POST /assets/<int:asset_id>/assign` | `user_id` (required); `project_id`, `request_id`, `due_back` |
| `POST /assignments/<int:assignment_id>/return` | `return_condition`, `send_to_maintenance` |
| `POST /requests` | `request_type`, `reason` (required); `item_name`, `asset_id`, `asset_type`, `category`, `quantity` (defaults to `1`), `amount`, `needed_by`, `project_id`. Asset requests need `item_name` or `asset_id`; disbursement requests need `amount` |
| `PATCH /requests/<int:request_id>/fulfil` | `asset_id` (optional; uses the request's asset when omitted) |
| `POST /procurements` | `item_name`, `asset_type`, `category`, `quantity`, `estimated_cost`, `supplier`, `reason`, `request_id`; `item_name` is required unless `request_id` is supplied |
| `PATCH /procurements/<int:procurement_id>` | `item_name`, `asset_type`, `category`, `quantity`, `estimated_cost`, `supplier`, `reason`, `action` (`submit`, `cancel`, or `purchased`); provide at least one field or `action` |
| `POST /projects` | `name` (required); `description`, `start_date`, `end_date` |
| `PATCH /projects/<int:project_id>` | `name`, `description`, `start_date`, `end_date` (at least one required) |
| `PATCH /projects/<int:project_id>/team` | `manager_id` (active user, only after approval), `staff_ids` (list of active staff user IDs); either field may be supplied |
| `POST /projects/<int:project_id>/submit` | `approver_ids` (required: non-empty ordered list of approver user IDs) |
| `PATCH /projects/<int:project_id>/status` | `status` (required), `reason`; status values: `approved`, `active`, `on_hold`, `completed`, `cancelled` |
| `POST /projects/<int:project_id>/milestones` | `title` (required), `description`, `due_date` |
| `PATCH /projects/<int:project_id>/milestones/<int:milestone_id>` | `status` (required: `planned`, `in_progress`, or `completed`) |
| `POST /api/disbursements` | `payee`, `recipient_phone`, `amount` (required); `description`, `currency` (`KES` only) |
| `POST /api/disbursements/<int:disbursement_id>/process` | Empty JSON body; payout must be approved before submission |

## Authentication

Send JSON to `POST /session/login` with a username or email and password. Keep the returned session cookie for later requests.

```bash
curl -i -c cookies.txt -X POST http://localhost:5000/session/login \
  -H "Content-Type: application/json" \
  -d '{"identifier":"staff","password":"Staff-demo-2026"}'

curl -b cookies.txt http://localhost:5000/requests
```

The supported roles are `admin`, `manager`, and `staff`. Managers handle inventory, asset assignment and fulfilment, procurement, and approvals. Access is checked against the user's current database role. Deactivated accounts cannot log in or continue using existing sessions. Applying `backend/schema.sql` converts existing `store_manager` accounts to `staff`.

Project access also includes the project's creator and assigned `manager_id`. Admins and managers can assign a project manager and staff to any project that is not completed or cancelled. Admins, managers, and the assigned project manager can manage milestones while a project is open. Completed and cancelled projects are locked against further edits.

## Frontend connection

The frontend can call the API at `http://localhost:5000` in development. Send login requests to `/session/login` and include credentials on later requests to use the session cookie. For browser integration, proxy API requests through the frontend's origin or configure Flask-CORS for the frontend origin with credentials enabled.

## Demo accounts

Run the seed script to insert the demo accounts and sample assets. It does not replace an existing user with the same username.

| Role | Username | Email | Demo password |
|---|---|---|---|
| Admin | `admin` | `admin@nexus.com` | `Admin-demo-2026` |
| Manager | `manager` | `manager@nexus.com` | `Manager-demo-2026` |
| Staff | `staff` | `staff@nexus.com` | `Staff-demo-2026` |

These credentials are for local development only. Do not use them in a deployed environment.

## Setup

Requirements: Python, PostgreSQL, and pip.

1. Create and activate a virtual environment, then install dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r backend/requirements.txt
   ```

2. Create a `.env` file in the repository root with a PostgreSQL connection URL and a strong Flask session key:

   ```dotenv
   DATABASE_URL=postgresql://username:password@localhost:5432/nexus
   SECRET_KEY=replace-with-a-long-random-value
   ```

3. Apply the schema and optionally load demo data:

   ```bash
   python -m backend.init_db
   python -m backend.seed
   ```

   The Flask app also applies the schema at startup. To create an initial admin instead of using the seeded demo admin, run:

   ```bash
   python -m backend.admin_accounts bootstrap-admin --username admin --email admin@example.com
   ```

   The command prompts for a password and only works when no admin account exists.

4. Start the development server:

   ```bash
   flask --app backend.app:create_app run --debug
   ```

   The API is available at `http://localhost:5000`; check `GET /health` for a health response.

## Database and tests

The schema is defined in `backend/schema.sql` and applied by `backend.init_db` or when the app starts. Running `python -m backend.init_db --reset` drops and recreates application tables
**NOTE:** This is destructive and should only be used with disposable development data.

Run tests with:

```bash
python -m pytest
```

Tests that construct the Flask app require a reachable PostgreSQL database configured through `DATABASE_URL`.

## Future work

- Connect a production payment provider.
- Add reporting and dashboard analytics.
- Expand notification delivery and operational reporting.
- Deploy the API with production-grade secrets, database operations, and monitoring.

## License and authors

This project is described as MIT-licensed. 
# Authors: 
1. David Manjari, 
2. Tereziah Mpaera, 
3. Trevor Kamanguya, 
4. Albashir Abdi, 
5. William Munene,
6. Enock Kibet.

GitHub: [Visit Project Repo](https://github.com/David-Manjari/Nexus_Backend)
