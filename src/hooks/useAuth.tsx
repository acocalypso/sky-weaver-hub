import { useEffect, useState, ReactNode } from "react";
import { getToken, setToken, SkyApi, type SkyUserPrincipal } from "@/lib/api";
import { AuthContext, type AuthCtx, type Role } from "@/hooks/auth-context";

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

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
