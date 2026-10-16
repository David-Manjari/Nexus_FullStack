import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { apiRequest } from "../api/http";

const AuthContext = createContext(null);

function mapUser(user) {
  return {
    id: user.user_id,
    name: user.username,
    email: user.email,
    role: user.role,
    roles: [user.role],
    department: null,
  };
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    // Restore identity from Flask's HttpOnly session cookie instead of localStorage.
    apiRequest("/session/me")
      .then(({ user: sessionUser }) => {
        if (active) setUser(mapUser(sessionUser));
      })
      .catch(() => {
        if (active) setUser(null);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  const login = async ({ email, password }) => {
    // The backend owns credential validation and sets the session cookie.
    const { user: sessionUser } = await apiRequest("/session/login", {
      method: "POST",
      body: { identifier: email, password },
    });
    const mappedUser = mapUser(sessionUser);
    setUser(mappedUser);
    return mappedUser;
  };

  const logout = async () => {
    try {
      await apiRequest("/session/logout", { method: "POST" });
    } finally {
      setUser(null);
    }
  };

  const value = useMemo(
    () => ({
      user,
      loading,
      login,
      logout,
      isAuthenticated: !!user,
    }),
    [user, loading]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }

  return context;
}
