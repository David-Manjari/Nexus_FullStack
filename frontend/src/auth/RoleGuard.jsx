import { Navigate } from "react-router-dom";
import { useAuth } from "./AuthContext";
import Loading from "../components/Loading";

export default function RoleGuard({
  allowedRoles = [],
  children,
  fallback = <Navigate to="/unauthorized" replace />,
}) {
  const { user, loading } = useAuth();

  if (loading) return <Loading message="Checking session..." />;

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  const userRoles = Array.isArray(user.roles) ? user.roles : [user.role];
  const hasAccess = allowedRoles.length === 0 || allowedRoles.some((role) => userRoles.includes(role));

  if (!hasAccess) {
    return fallback;
  }

  return children;
}
