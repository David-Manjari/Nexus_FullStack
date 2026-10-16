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

const ALL_ROLES = ["admin", "manager", "store_manager", "staff"];
const APPROVER_ROLES = ["admin", "manager"];
const PROCUREMENT_READ_ROLES = ["admin", "manager", "store_manager"];
const PROCUREMENT_WRITE_ROLES = ["admin", "store_manager"];


function getActivePage(pathname) {
  const pageId = pathname.replace(/^\/+/, "").split("/")[0];
  return PAGE_LINKS.find((page) => page.id === pageId) ?? PAGE_LINKS[0];
}

function DashboardHome() {
  const { user } = useAuth();
  const [unreadCount, setUnreadCount] = useState(0);

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

  return (
    <div style={{ display: "grid", gap: "16px" }}>
      <p style={{ margin: 0, color: "#475569", fontSize: "1.4rem", fontWeight: 600 }}>
        Welcome back,
      </p>
      <h1 style={{ margin: 0 }}>Operations dashboard</h1>
      <div style={{ display: "flex", gap: "14px", flexWrap: "wrap", marginTop: "4px" }}>
        <span
          style={{
            background: "#eff6ff",
            color: "#1d4ed8",
            padding: "18px 24px",
            borderRadius: "999px",
            fontSize: "1.5rem",
            fontWeight: 700,
          }}
        >
          Role: {user?.role}
        </span>
        <span
          style={{
            background: "#f1f5f9",
            color: "#334155",
            padding: "18px 24px",
            borderRadius: "999px",
            fontSize: "1.5rem",
            fontWeight: 700,
          }}
        >
          Department: {user?.department || "Not set"}
        </span>
      </div>

      <Link
        to="/notifications"
        style={{
          display: "block",
          width: "100%",
          maxWidth: "320px",
          background: "#fee2e2",
          color: "#991b1b",
          padding: "12px 16px",
          borderRadius: 0,
          fontSize: "1.1rem",
          fontWeight: 700,
          textDecoration: "none",
          boxSizing: "border-box",
          border: "1px solid #fca5a5",
          cursor: "pointer",
          lineHeight: 1.4,
        }}
      >
        {unreadCount > 0 ? "Click here to view unread notifications" : "Click here to view notifications"}
      </Link>
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
          <Route path="/disbursements" element={<RoleGuard allowedRoles={APPROVER_ROLES}><Disbursements /></RoleGuard>} />
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