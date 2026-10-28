import React, { useEffect, useState } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  Outlet,
  useLocation,
  Link,
} from "react-router-dom";

import { getUnreadCount } from "./api/notifications";
import { getAssignedProjects, getProjects } from "./api/projects";
import { getDisbursements } from "./api/disbursements";
import { getMyRequests } from "./api/requests";
import { getProcurements } from "./api/procurement";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import ProtectedRoute from "./auth/ProtectedRoute";
import RoleGuard from "./auth/RoleGuard";
import AppLayout from "./layouts/AppLayout";
import { PAGE_LINKS } from "./layouts/Navbar";
import LoginPage from "./pages/auth/LoginPage";
import UnauthorizedPage from "./pages/UnauthorizedPage";
import AdminUsersPage from "./pages/admin/AdminUsersPage";
import AdminRolesPage from "./pages/admin/AdminRolesPage";
import Approvals from "./pages/approvals/Approvals";
import Disbursements from "./pages/disbursements/Disbursements";
import NotificationsPage from "./pages/notifications/NotificationsPage";
import ProjectsPage from "./pages/projects/ProjectsPage";
import Loading from "./components/Loading";

import InventoryPage from "./pages/inventory/InventoryPage";

import MyRequests from "./pages/requests/MyRequests";
import RequestForm from "./pages/requests/RequestForm";
import ProcurementQueue from "./pages/procurement/ProcurementQueue";
import ProcurementForm from "./pages/procurement/ProcurementForm";

const ALL_ROLES = ["admin", "manager", "staff"];
const APPROVER_ROLES = ["admin", "manager"];
const PROCUREMENT_READ_ROLES = ["admin", "manager"];
const PROCUREMENT_WRITE_ROLES = ["manager"];


function getActivePage(pathname) {
  const pageId = pathname.replace(/^\/+/, "").split("/")[0];
  return PAGE_LINKS.find((page) => page.id === pageId) ?? PAGE_LINKS[0];
}

function DashboardHome() {
  const { user } = useAuth();
  const [unreadCount, setUnreadCount] = useState(0);
  const [projects, setProjects] = useState([]);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [projectsError, setProjectsError] = useState("");
  const [disbursements, setDisbursements] = useState([]);
  const [disbursementsLoading, setDisbursementsLoading] = useState(true);
  const [disbursementsError, setDisbursementsError] = useState("");
  const [requests, setRequests] = useState([]);
  const [requestsLoading, setRequestsLoading] = useState(true);
  const [requestsError, setRequestsError] = useState("");
  const [procurements, setProcurements] = useState([]);
  const [procurementsLoading, setProcurementsLoading] = useState(true);
  const [procurementsError, setProcurementsError] = useState("");
  const isStaff = user?.role === "staff";
  const canViewProcurements = ["admin", "manager"].includes(user?.role);

  useEffect(() => {
    if (!user) return;

    let active = true;

    async function loadUnreadCount() {
      try {
        const count = await getUnreadCount(user.id);
        if (active) setUnreadCount(count);
      } catch {
        if (active) setUnreadCount(0);
      }
    }

    loadUnreadCount();
    return () => {
      active = false;
    };
  }, [user]);

  useEffect(() => {
    if (!user) return undefined;
    let active = true;
    setProjects([]);
    setProjectsLoading(true);
    setProjectsError("");

    (isStaff ? getAssignedProjects() : getProjects())
      .then((data) => {
        if (active) setProjects(data);
      })
      .catch((loadError) => {
        if (active) setProjectsError(loadError.message || "Could not load project status.");
      })
      .finally(() => {
        if (active) setProjectsLoading(false);
      });

    return () => {
      active = false;
    };
  }, [user?.id, user?.role]);

  useEffect(() => {
    if (!user) return undefined;
    let active = true;
    setDisbursements([]);
    setDisbursementsLoading(true);
    setDisbursementsError("");
    setRequests([]);
    setRequestsLoading(true);
    setRequestsError("");

    getDisbursements()
      .then((data) => {
        if (active) setDisbursements(data);
      })
      .catch((loadError) => {
        if (active) {
          setDisbursementsError(loadError.message || "Could not load your disbursement requests.");
        }
      })
      .finally(() => {
        if (active) setDisbursementsLoading(false);
      });

    getMyRequests()
      .then((data) => {
        if (active) setRequests(data);
      })
      .catch((loadError) => {
        if (active) setRequestsError(loadError.message || "Could not load your requests.");
      })
      .finally(() => {
        if (active) setRequestsLoading(false);
      });

    return () => {
      active = false;
    };
  }, [user?.id]);

  useEffect(() => {
    if (!canViewProcurements) {
      setProcurements([]);
      setProcurementsLoading(false);
      setProcurementsError("");
      return undefined;
    }

    let active = true;
    setProcurements([]);
    setProcurementsLoading(true);
    setProcurementsError("");

    getProcurements()
      .then((data) => {
        if (active) setProcurements(data);
      })
      .catch((loadError) => {
        if (active) {
          setProcurementsError(loadError.message || "Could not load procurements.");
        }
      })
      .finally(() => {
        if (active) setProcurementsLoading(false);
      });

    return () => {
      active = false;
    };
  }, [canViewProcurements, user?.id]);

  return (
    <div style={{ display: "grid", gap: "16px" }}>
      <p style={{ margin: 0, color: "var(--color-muted)", fontSize: "1.1rem", fontWeight: 600 }}>
        Welcome back,
      </p>
      <h1 style={{ margin: 0 }}>Operations dashboard</h1>
      <div style={{ display: "flex", gap: "14px", flexWrap: "wrap", marginTop: "4px" }}>
        <span
          style={{
            background: "var(--color-primary-soft)",
            color: "var(--color-primary)",
            padding: "12px 18px",
            borderRadius: "12px",
            fontSize: "1rem",
            fontWeight: 700,
          }}
        >
          Role: {user?.role}
        </span>
      </div>

      <Link
        to="/notifications"
        style={{
          display: "block",
          width: "100%",
          maxWidth: "320px",
          background: "var(--color-primary-soft)",
          color: "var(--color-primary)",
          padding: "12px 16px",
          borderRadius: "8px",
          fontSize: "1rem",
          fontWeight: 700,
          textDecoration: "none",
          boxSizing: "border-box",
          border: "1px solid var(--color-border)",
          cursor: "pointer",
          lineHeight: 1.4,
        }}
      >
        {unreadCount > 0 ? "Click here to view unread notifications" : "Click here to view notifications"}
      </Link>

      <section className="dashboard-projects" aria-labelledby="dashboard-projects-heading">
        <div className="dashboard-projects__header">
          <h2 id="dashboard-projects-heading">
            {isStaff ? "Projects you are assigned to" : "Project status and audit"}
          </h2>
          <Link className="dashboard-projects__view-all" to="/projects">View all</Link>
        </div>
        {projectsLoading && <Loading message="Loading project status..." />}
        {!projectsLoading && projectsError && <p role="alert">{projectsError}</p>}
        {!projectsLoading && !projectsError && projects.length === 0 && (
          <p>{isStaff ? "You are not assigned to any projects." : "No projects are available to you."}</p>
        )}
        {!projectsLoading && !projectsError && projects.length > 0 && (
          <ul className="dashboard-projects__list">
            {projects.slice(0, 4).map((project) => (
              <li key={project.id} className="dashboard-projects__item">
                <div className="dashboard-projects__title">
                  <strong>{project.name}</strong>
                  <span className={`project-status project-status--${project.status}`}>
                    {project.status.replaceAll("_", " ")}
                  </span>
                </div>
                {project.statusAudit.length > 0 ? (
                  <ol className="dashboard-projects__audit">
                    {project.statusAudit.map((entry) => (
                      <li key={entry.id}>
                        <span>
                          {entry.fromStatus ? `${entry.fromStatus.replaceAll("_", " ")} to ` : "Created as "}
                          {entry.toStatus.replaceAll("_", " ")}
                        </span>
                        {entry.reason && <span> · {entry.reason}</span>}
                        <small>
                          {entry.changedByName ? ` by ${entry.changedByName}` : ""}
                          {entry.changedAt ? ` · ${new Date(entry.changedAt).toLocaleString()}` : ""}
                        </small>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p>No status changes recorded.</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <>
        <section className="dashboard-projects" aria-labelledby="dashboard-disbursements-heading">
          <div className="dashboard-projects__header">
            <h2 id="dashboard-disbursements-heading">
              {isStaff ? "My disbursement requests" : "Disbursements"}
            </h2>
            <Link className="dashboard-projects__view-all" to="/disbursements">View all</Link>
          </div>
          {disbursementsLoading && <Loading message="Loading disbursements..." />}
          {!disbursementsLoading && disbursementsError && (
            <p role="alert">{disbursementsError}</p>
          )}
          {!disbursementsLoading && !disbursementsError && disbursements.length === 0 && (
            <p>{isStaff ? "You have not sent any disbursement requests." : "No disbursements found."}</p>
          )}
          {!disbursementsLoading && !disbursementsError && disbursements.length > 0 && (
            <ul className="dashboard-projects__list">
              {disbursements.slice(0, 4).map((disbursement) => (
                <li key={disbursement.id} className="dashboard-projects__item">
                  <div className="dashboard-projects__title">
                    <strong>{disbursement.recipient}</strong>
                    <span>{disbursement.approvalStatus || disbursement.status}</span>
                  </div>
                  <p>{disbursement.reference} · {disbursement.amount}</p>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="dashboard-projects" aria-labelledby="dashboard-requests-heading">
          <div className="dashboard-projects__header">
            <h2 id="dashboard-requests-heading">{isStaff ? "My requests" : "Requests"}</h2>
            <Link className="dashboard-projects__view-all" to="/requests">View all</Link>
          </div>
          {requestsLoading && <Loading message="Loading requests..." />}
          {!requestsLoading && requestsError && <p role="alert">{requestsError}</p>}
          {!requestsLoading && !requestsError && requests.length === 0 && (
            <p>{isStaff ? "You have not sent any requests." : "No requests found."}</p>
          )}
          {!requestsLoading && !requestsError && requests.length > 0 && (
            <ul className="dashboard-projects__list">
              {requests.slice(0, 4).map((request) => (
                <li key={request.id} className="dashboard-projects__item">
                  <div className="dashboard-projects__title">
                    <strong>{request.itemName}</strong>
                    <span>{request.status}</span>
                  </div>
                  <p>{request.reason}</p>
                </li>
              ))}
            </ul>
          )}
        </section>

        {canViewProcurements && (
          <section className="dashboard-projects" aria-labelledby="dashboard-procurements-heading">
            <div className="dashboard-projects__header">
              <h2 id="dashboard-procurements-heading">Procurements</h2>
              <Link className="dashboard-projects__view-all" to="/procurement">View all</Link>
            </div>
            {procurementsLoading && <Loading message="Loading procurements..." />}
            {!procurementsLoading && procurementsError && <p role="alert">{procurementsError}</p>}
            {!procurementsLoading && !procurementsError && procurements.length === 0 && (
              <p>No procurements found.</p>
            )}
            {!procurementsLoading && !procurementsError && procurements.length > 0 && (
              <ul className="dashboard-projects__list">
                {[...procurements]
                  .sort((left, right) => new Date(right.createdAt) - new Date(left.createdAt))
                  .slice(0, 4)
                  .map((procurement) => (
                  <li key={procurement.id} className="dashboard-projects__item">
                    <div className="dashboard-projects__title">
                      <strong>{procurement.itemName}</strong>
                      <span>{procurement.status.replaceAll("_", " ")}</span>
                    </div>
                    <p>
                      {procurement.quantity} × {procurement.itemType}
                      {procurement.estimatedCost != null
                        ? ` · KES ${Number(procurement.estimatedCost).toLocaleString()}`
                        : ""}
                    </p>
                  </li>
                  ))}
              </ul>
            )}
          </section>
        )}
      </>
    </div>
  );
}

function Shell() {
  const { pathname } = useLocation();
  const activePage = getActivePage(pathname);

  return (
    <AppLayout activePage={activePage.id}>
      <main className="page-content">
        <p className="page-eyebrow">Nexus workspace</p>
        <Outlet />
      </main>
    </AppLayout>
  );
}

function AppRoutes() {
  const { user, loading } = useAuth();

  if (loading) return <Loading message="Connecting to Nexus..." />;

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<Navigate to={user ? "/dashboard" : "/login"} replace />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<Shell />}>
          <Route path="/dashboard" element={<DashboardHome />} />
          <Route path="/approvals" element={<RoleGuard allowedRoles={APPROVER_ROLES}><Approvals /></RoleGuard>} />
          <Route path="/disbursements" element={<RoleGuard allowedRoles={ALL_ROLES}><Disbursements /></RoleGuard>} />
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/requests" element={<RoleGuard allowedRoles={ALL_ROLES}><MyRequests /></RoleGuard>} />
          <Route path="/requests/new" element={<RoleGuard allowedRoles={ALL_ROLES}><RequestForm /></RoleGuard>} />
          <Route path="/procurement" element={<RoleGuard allowedRoles={PROCUREMENT_READ_ROLES}><ProcurementQueue /></RoleGuard>} />
          <Route path="/procurement/new" element={<RoleGuard allowedRoles={PROCUREMENT_WRITE_ROLES}><ProcurementForm /></RoleGuard>} />
          <Route path="/projects" element={<RoleGuard allowedRoles={ALL_ROLES}><ProjectsPage /></RoleGuard>} />

          <Route
            path="/inventory"
            element={
              <RoleGuard allowedRoles={ALL_ROLES}>
                <Navigate to="/inventory/tools" replace />
              </RoleGuard>
            }/>

          <Route
            path="/inventory/tools"
            element={
              <RoleGuard allowedRoles={ALL_ROLES}>
                <InventoryPage type="tool" />
              </RoleGuard>
            }/>

          <Route
            path="/inventory/devices"
            element={
              <RoleGuard allowedRoles={ALL_ROLES}>
                <InventoryPage type="device" />
              </RoleGuard>
            }/>

          <Route
            path="/inventory/vehicles"
            element={
              <RoleGuard allowedRoles={ALL_ROLES}>
                <InventoryPage type="vehicle" />
              </RoleGuard>
            }/>

          <Route
            path="/admin"
            element={
              <RoleGuard allowedRoles={["admin"]}>
                <Navigate to="/admin/users" replace />
              </RoleGuard>
            }
          />

          <Route
            path="/admin/users"
            element={
              <RoleGuard allowedRoles={["admin"]}>
                <AdminUsersPage />
              </RoleGuard>
            }
          />

          <Route
            path="/admin/roles"
            element={
              <RoleGuard allowedRoles={["admin"]}>
                <AdminRolesPage />
              </RoleGuard>
            }
          />
        </Route>
      </Route>

      <Route path="/unauthorized" element={<UnauthorizedPage />} />
      <Route path="*" element={<Navigate to={user ? "/dashboard" : "/login"} replace />} />
    </Routes>
  );
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;