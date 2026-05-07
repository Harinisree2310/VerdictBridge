import { createContext, useContext, useState, useEffect, useCallback } from "react";

const AuthContext = createContext(null);

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

export function AuthProvider({ children }) {
  const [user, setUser]     = useState(null);
  const [token, setToken]   = useState(() => localStorage.getItem("auth_token"));
  const [loading, setLoading] = useState(true);

  // ── Fetch current user profile ─────────────────────────────────────────────
  const fetchMe = useCallback(async (accessToken) => {
    try {
      const res = await fetch(`${API}/auth/me`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        setUser(await res.json());
        return true;
      }
      // Token invalid / expired
      localStorage.removeItem("auth_token");
      setToken(null);
      setUser(null);
      return false;
    } catch {
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (token) {
      fetchMe(token);
    } else {
      setLoading(false);
    }
  }, [token, fetchMe]);

  // ── Login — uses JSON endpoint to avoid form-encoding issues ───────────────
  async function login(email, password) {
    const res = await fetch(`${API}/auth/login/json`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: email.trim().toLowerCase(),
        password,
      }),
    });

    if (!res.ok) {
      let detail = "Login failed. Check your credentials.";
      try {
        const err = await res.json();
        detail = err.detail ?? detail;
      } catch { /* ignore parse errors */ }
      throw new Error(detail);
    }

    const data = await res.json();
    localStorage.setItem("auth_token", data.access_token);
    setToken(data.access_token);
    await fetchMe(data.access_token);
  }

  // ── Logout ─────────────────────────────────────────────────────────────────
  function logout() {
    localStorage.removeItem("auth_token");
    setToken(null);
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, token, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
