import { createContext, useContext, useMemo, useState } from "react";
import api from "../api/client";

const AuthContext = createContext(null);

function b64UrlDecode(input) {
  const base64 = input.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "=");
  return atob(padded);
}

function isJwtExpired(token) {
  if (!token) return true;
  try {
    const parts = token.split(".");
    if (parts.length < 2) return true;
    const payload = JSON.parse(b64UrlDecode(parts[1]));
    const exp = Number(payload?.exp);
    if (!Number.isFinite(exp)) return true;
    const now = Math.floor(Date.now() / 1000);
    return exp <= now;
  } catch {
    return true;
  }
}

function loadValidAuthFromStorage() {
  const storedToken = localStorage.getItem("trustagent_token") || "";
  const storedUser = localStorage.getItem("trustagent_user") || "";
  if (!storedToken) return { token: "", user: "" };
  if (isJwtExpired(storedToken)) {
    localStorage.removeItem("trustagent_token");
    localStorage.removeItem("trustagent_user");
    return { token: "", user: "" };
  }
  return { token: storedToken, user: storedUser };
}

export function AuthProvider({ children }) {
  const initial = loadValidAuthFromStorage();
  const [token, setToken] = useState(initial.token);
  const [user, setUser] = useState(initial.user);

  const login = async (username, password) => {
    const res = await api.post("/auth/token", { username, password });
    const accessToken = res.data.access_token;
    localStorage.setItem("trustagent_token", accessToken);
    localStorage.setItem("trustagent_user", username);
    setToken(accessToken);
    setUser(username);
  };

  const register = async (username, password) => {
    await api.post("/auth/register", { username, password, role: "analyst" });
  };

  const logout = () => {
    localStorage.removeItem("trustagent_token");
    localStorage.removeItem("trustagent_user");
    setToken("");
    setUser("");
  };

  const value = useMemo(
    () => ({
      token,
      user,
      isAuthenticated: Boolean(token),
      login,
      register,
      logout,
    }),
    [token, user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
