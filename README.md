# Nexus

Nexus is a role-aware operations workspace for organizations that manage project and field work. It brings inventory, item requests, procurement, approvals, and disbursements into one interface, with the goal of replacing fragmented paper forms, spreadsheets, and chat-based workflows.

> **Project status:** This repository contains a React/Vite frontend and a Flask/PostgreSQL backend. The frontend and backend setup details are documented below and in [backend/README.md](backend/README.md).

## Why Nexus

Teams need a reliable way to know what tools, devices, and vehicles are available, who has been assigned an item, and what needs repair. They also need a traceable path from a worker's request through procurement and approval to a payout. Without shared visibility, requests can be delayed or lost, approvals can stall, and payments can be difficult to tie back to their purpose and approver.

Nexus is intended to give:

- **Staff** a place to request tools and other items and follow request status.
- **Managers and approvers** a workspace to review operational and spending requests.
- **Owners and administrators** visibility into system activity, users, and access.
- **Inventory managers** tools to maintain stock, assign items, and record returns.

## Current features

- Demo login with role-aware protected routes and a browser-stored session.
- Operations dashboard with the signed-in user's role and department.
- Inventory pages for tools, devices, and vehicles, including search and category/status filters.
- Inventory item creation, editing, deletion, assignment, return, and assignment history.
- Staff item requests, request status timelines, and automatic procurement drafts when an item is unavailable.
- Procurement request creation, editing of drafts, and escalation for approval.
- An approvals queue with approve/reject actions and optional comments.
- A disbursement queue with pending, processing, paid, and failed states.
- Notifications page and notification bell, with read/unread state, escalation alerts for approvers, and decision updates for requesters.
- Admin pages for user and role administration.
- Loading, empty, unauthorized, and error states in relevant workflows.

### Routes

| Route | Page | Access |
| --- | --- | --- |
| `/login` | Demo sign-in | Public |
| `/dashboard` | Operations dashboard | Signed-in users |
| `/inventory/tools` | Tools inventory | Manager, admin (manage: manager) |
| `/inventory/devices` | Devices inventory | Manager, admin (manage: manager) |
| `/inventory/vehicles` | Vehicles inventory | Manager, admin (manage: manager) |
| `/requests` | My requests | Staff, admin |
| `/requests/new` | Submit an item request | Staff, admin |
| `/procurement` | Procurement queue | Manager |
| `/procurement/new` | Create a procurement request | Manager |
| `/approvals` | Review approval items | Signed-in users |
| `/disbursements` | Manage payout statuses | Signed-in users |
| `/notifications` | View notifications | Signed-in users |
| `/admin/users` | User administration | Admin |
| `/admin/roles` | Role administration | Admin |

The navigation currently includes a **Projects** link, but a projects or company-history page is not implemented in this prototype. The brief's project dashboard/history, task assignment and acceptance workflow, payment receipts, and a full product catalog experience remain future work.

## Demo accounts

Use one of these accounts on the login page:

| Role | Email | Password |
| --- | --- | --- |
| Admin | `admin@nexus.com` | `admin123` |
| Manager | `manager@nexus.com` | `manager123` |
| Staff | `staff@nexus.com` | `staff123` |

These credentials are for local demonstration only. Authentication is simulated in the frontend and does not provide production security.

## Tech stack and data

- React 
- React Router 
- Vite 
- JavaScript 

Most workflows use in-memory mock data. The demo session, approval decisions, and payout statuses use browser `localStorage`; there is no shared persistence or server-side authorization. 
Tools come from local mock data. Device and vehicle catalog items are loaded from [DummyJSON](https://dummyjson.com/) .Product categories and adapted for the inventory UI.

## Project structure

```text
frontend/
  src/
    api/       Data access modules for inventory, requests, procurement, users, and notifications
    auth/      Demo session context and route guards
    components/ Shared loading, empty, error, and notification components
    layouts/   Application navigation and page shell
    mock/      Temporary inventory, request, and procurement data
    pages/     Authentication, inventory, requests, procurement, approvals, disbursements, and admin pages
```
## Getting started

Requirements: Node.js and npm.

```bash
cd frontend
npm install
npm run dev
```

Vite prints the local development URL when the server starts.

## Backend API

The Flask API uses PostgreSQL. From the repository root, create a Python virtual environment, install the backend requirements, configure `DATABASE_URL` and `SECRET_KEY` as described in [backend/README.md](backend/README.md), then start the API:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
flask --app backend.app:create_app run --debug
```

The API is available at `http://localhost:5000`; the health check is `http://localhost:5000/health`.

## Free Render demo deployment

The root [render.yaml](render.yaml) describes a free Render static frontend, free Flask web service, and free PostgreSQL database. To deploy, push the repository to GitHub, sign in to Render, choose **New > Blueprint**, connect the repository, and apply the Blueprint.

The free PostgreSQL database is temporary and is deleted after 30 days. The free backend may sleep when idle, so its first request after inactivity can be delayed. Export the database or migrate it before the 30-day expiry if you need to retain data. This setup is for a short demo, not production or durable storage.

After the services are created, bootstrap the first admin from a trusted local terminal using the database's external connection URL from the Render dashboard. Enter the URL without echoing it or saving it in shell history:

```bash
read -r -s -p 'Render external DATABASE_URL: ' DATABASE_URL
echo
export DATABASE_URL
python -m backend.admin_accounts bootstrap-admin --username your-admin-name --email you@example.com
```

The command prompts for a password and confirmation; do not use the local demo credentials. The generated `SECRET_KEY` must be kept stable across deploys, since MFA secrets are encrypted using it. Daraja payouts remain disabled in this demo by default. The default frontend and backend URLs in `render.yaml` assume the service names shown there; update `FRONTEND_ORIGINS` and `VITE_API_BASE_URL` if Render assigns different hostnames or you rename either service.

## Future Improvements

- Implement reporting for the manager or owner
- Streamline access for the users while restricting others
- Add dashboard analytics for all users
- Create a company wide database.
- Add durable production hosting and database backups

## License

This project is licensed under the MIT License.

## Authors

- David Manjari
- Tereziah Mpaera
- Trevor Kamanguya
- Albashir Abdi
- William Munene
- Enock Kibet




GitHub: https://github.com/David-Manjari
