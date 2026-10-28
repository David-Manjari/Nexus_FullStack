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
import { getProjects } from "./api/projects";
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
const PROCUREMENT_READ_ROLES = ["manager"];
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
    let active = true;

    getProjects()
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
  }, []);

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
          <h2 id="dashboard-projects-heading">Project status and audit</h2>
          <Link to="/projects">Projects</Link>
        </div>
        {projectsLoading && <Loading message="Loading project status..." />}
        {!projectsLoading && projectsError && <p role="alert">{projectsError}</p>}
        {!projectsLoading && !projectsError && projects.length === 0 && (
          <p>No projects are assigned or available to you.</p>
        )}
        {!projectsLoading && !projectsError && projects.length > 0 && (
          <ul className="dashboard-projects__list">
            {projects.map((project) => (
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