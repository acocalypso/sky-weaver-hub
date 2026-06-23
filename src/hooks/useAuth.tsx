import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { getToken, setToken, SkyApi, type SkyUserPrincipal } from "@/lib/api";

type Role = "admin" | "operator" | "viewer";

interface AuthCtx {
  user: SkyUserPrincipal | null;
  token: string | null;
  loading: boolean;
  roles: Role[];
  isAdmin: boolean;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const Ctx = createContext<AuthCtx | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [tokenState, setTokenState] = useState<string | null>(getToken());
  const [user, setUser] = useState<SkyUserPrincipal | null>(null);
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    async function load() {
      if (!getToken()) {
        setLoading(false);
        return;
      }
      try {
        const principal = await SkyApi.me();
        if (!alive) return;
        setUser(principal);
        setRoles([principal.role as Role]);
      } catch {
        setToken(null);
        setTokenState(null);
        setUser(null);
        setRoles([]);
      } finally {
        if (alive) setLoading(false);
      }
    }
    load();
    return () => { alive = false; };
  }, []);

  async function signIn(username: string, password: string) {
    const data = await SkyApi.login(username, password);
    setToken(data.token);
    setTokenState(data.token);
    const principal = await SkyApi.me();
    setUser(principal);
    setRoles([principal.role as Role]);
  }

  const value: AuthCtx = {
    user,
    token: tokenState,
    loading,
    roles,
    isAdmin: roles.includes("admin"),
    signIn,
    signOut: async () => {
      setToken(null);
      setTokenState(null);
      setUser(null);
      setRoles([]);
    },
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth must be used inside AuthProvider");
  return c;
}
