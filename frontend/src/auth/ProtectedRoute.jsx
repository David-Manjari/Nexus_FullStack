import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "./AuthContext";
import Loading from "../components/Loading";

export default function ProtectedRoute() {
  const { user, loading } = useAuth();

  if (loading) return <Loading message="Checking session..." />;

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}
