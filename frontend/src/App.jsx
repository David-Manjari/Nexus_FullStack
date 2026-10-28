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
  const [activityCategory, setActivityCategory] = useState("all");
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

  const activityItems = [
    ...projects.map((project) => ({
      id: `project-${project.id}`,
      category: "projects",
      label: "Project",
      title: project.name,
      status: project.status.replaceAll("_", " "),
      summary: project.description,
      date: project.createdAt,
    })),
    ...disbursements.map((disbursement) => ({
      id: `disbursement-${disbursement.id}`,
      category: "disbursements",
      label: "Disbursement",
      title: disbursement.recipient,
      status: disbursement.approvalStatus || disbursement.status,
      summary: `${disbursement.reference} · ${disbursement.amount}`,
      date: disbursement.date,
    })),
    ...requests.map((request) => ({
      id: `request-${request.id}`,
      category: "requests",
      label: "Request",
      title: request.itemName,
      status: request.status,
      summary: request.reason,
      date: request.createdAt,
    })),
    ...(canViewProcurements
      ? procurements.map((procurement) => ({
        id: `procurement-${procurement.id}`,
        category: "procurement",
        label: "Procurement",
        title: procurement.itemName,
        status: procurement.status.replaceAll("_", " "),
        summary: `${procurement.quantity} × ${procurement.itemType}${
          procurement.estimatedCost != null
            ? ` · KES ${Number(procurement.estimatedCost).toLocaleString()}`
            : ""
        }`,
        date: procurement.createdAt,
      }))
      : []),
  ].sort((left, right) => new Date(right.date || 0) - new Date(left.date || 0));
  const visibleActivity = activityItems
    .filter((item) => activityCategory === "all" || item.category === activityCategory)
    .slice(0, 4);
  const activityLoading =
    projectsLoading || disbursementsLoading || requestsLoading ||
    (canViewProcurements && procurementsLoading);
  const activityErrors = [
    projectsError,
    disbursementsError,
    requestsError,
    canViewProcurements ? procurementsError : "",
  ].filter(Boolean);

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

      <div className="dashboard-projects__top-controls">
        <nav className="dashboard-projects__page-links" aria-label="View all dashboard categories">
          <Link className="dashboard-projects__view-all" to="/projects">View all projects</Link>
          <Link className="dashboard-projects__view-all" to="/disbursements">View all disbursements</Link>
          <Link className="dashboard-projects__view-all" to="/requests">View all requests</Link>
          {canViewProcurements && (
            <Link className="dashboard-projects__view-all" to="/procurement">View all procurements</Link>
          )}
        </nav>
        <Link className="dashboard-projects__view-all" to="/notifications">
          {unreadCount > 0 ? `View notifications (${unreadCount})` : "View notifications"}
        </Link>
      </div>

      <section className="dashboard-projects" aria-labelledby="dashboard-activity-heading">
        <div className="dashboard-projects__header">
          <h2 id="dashboard-activity-heading">Recent activity</h2>
          <label className="dashboard-projects__filter">
            Category
            <select
              value={activityCategory}
              onChange={(event) => setActivityCategory(event.target.value)}
            >
              <option value="all">All categories</option>
              <option value="projects">Projects</option>
              <option value="disbursements">Disbursements</option>
              <option value="requests">Requests</option>
              {canViewProcurements && <option value="procurement">Procurements</option>}
            </select>
          </label>
        </div>
        {activityLoading && <Loading message="Loading recent activity..." />}
        {!activityLoading && activityErrors.map((message) => (
          <p key={message} role="alert">{message}</p>
        ))}
        {!activityLoading && visibleActivity.length === 0 && (
          <p>
            {activityItems.length === 0
              ? "No recent activity found."
              : "No recent activity in this category."}
          </p>
        )}
        {!activityLoading && visibleActivity.length > 0 && (
          <ul className="dashboard-projects__list">
            {visibleActivity.map((item) => (
              <li key={item.id} className="dashboard-projects__item">
                <div className="dashboard-projects__title">
                  <div className="dashboard-projects__activity-heading">
                    <span className="dashboard-projects__category">{item.label}</span>
                    <strong>{item.title}</strong>
                  </div>
                  <span className="project-status">{item.status}</span>
                </div>
                {item.summary && <p>{item.summary}</p>}
                {item.date && <small>{new Date(item.date).toLocaleString()}</small>}
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