import React, { createContext, useContext, useEffect, useState } from "react";
import { api, getToken, setToken } from "./api";

interface AuthCtx {
  token: string | null;
  username: string | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const Ctx = createContext<AuthCtx>({
  token: null,
  username: null,
  loading: false,
  login: async () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setTok] = useState<string | null>(getToken());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // valida el token contra el backend al montar (no se confía en el cliente)
    if (!token) {
      setLoading(false);
      return;
    }
    api
      .get("/api/health")
      .catch(() => setToken(null))
      .finally(() => setLoading(false));
  }, [token, setLoading]);

  const login = async (username: string, password: string) => {
    const data = await api.post<{ token: string; username: string }>(
      "/api/auth/login",
      { username, password }
    );
    setToken(data.token);
    setTok(data.token);
  };

  const logout = () => {
    api.post("/api/auth/logout").catch(() => {});
    setToken(null);
    setTok(null);
  };

  return (
    <Ctx.Provider value={{ token, username: null, loading, login, logout }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAuth() {
  return useContext(Ctx);
}
