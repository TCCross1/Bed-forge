import React, { createContext, useContext, useEffect, useRef, useState } from "react";
import api, { clearToken, storeToken } from "../lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const idleRef = useRef(Date.now());

  useEffect(() => {
    const legacy = localStorage.getItem("bf_token");
    if (legacy && !sessionStorage.getItem("bf_token")) {
      sessionStorage.setItem("bf_token", legacy);
      localStorage.removeItem("bf_token");
    }
    api.get("/auth/me")
      .then((res) => setUser(res.data))
      .catch(() => {
        clearToken();
        setUser(false);
      })
      .finally(() => setReady(true));
  }, []);

  useEffect(() => {
    const bump = () => { idleRef.current = Date.now(); };
    ["pointerdown", "keydown", "touchstart"].forEach((evt) => window.addEventListener(evt, bump));
    const timer = setInterval(() => {
      if (!user) return;
      if (Date.now() - idleRef.current > 30 * 60 * 1000) {
        logout();
      }
    }, 30000);
    return () => {
      ["pointerdown", "keydown", "touchstart"].forEach((evt) => window.removeEventListener(evt, bump));
      clearInterval(timer);
    };
  }, [user]);

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    storeToken(data.access_token);
    setUser(data.user);
    return data.user;
  };

  const logout = async () => {
    try {
      await api.post("/auth/logout");
    } catch (err) {
      console.error("[auth] logout", err);
    }
    clearToken();
    setUser(false);
  };

  const changePassword = async (current_password, new_password) => {
    await api.post("/auth/password", { current_password, new_password });
    const { data } = await api.get("/auth/me");
    setUser(data);
  };

  return (
    <AuthContext.Provider value={{ user, ready, login, logout, changePassword }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
