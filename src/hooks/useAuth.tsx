import { useEffect, useRef, useState, ReactNode } from "react";
import { getToken, setToken, SkyApi, type SkyUserPrincipal } from "@/lib/api";
import { AuthContext, type AuthCtx, type Role } from "@/hooks/auth-context";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [tokenState, setTokenState] = useState<string | null>(getToken());
  const [user, setUser] = useState<SkyUserPrincipal | null>(null);
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const authVersion = useRef(0);

  useEffect(() => {
    let alive = true;
    const version = authVersion.current;
    const token = getToken();
    const isCurrent = () => alive && version === authVersion.current && getToken() === token;
    async function load() {
      if (!token) {
        setLoading(false);
        return;
      }
      try {
        const principal = await SkyApi.me();
        if (!isCurrent()) return;
        setUser(principal);
        setRoles([principal.role as Role]);
      } catch {
        if (!isCurrent()) return;
        setToken(null);
        setTokenState(null);
        setUser(null);
        setRoles([]);
      } finally {
        if (alive && version === authVersion.current) setLoading(false);
      }
    }
    load();
    return () => { alive = false; authVersion.current += 1; };
  }, []);

  async function signIn(username: string, password: string) {
    const version = ++authVersion.current;
    setLoading(true);
    try {
      const data = await SkyApi.login(username, password);
      if (version !== authVersion.current) return;
      setToken(data.token);
      setTokenState(data.token);
      const principal = await SkyApi.me();
      if (version !== authVersion.current) return;
      setUser(principal);
      setRoles([principal.role as Role]);
    } catch (error) {
      if (version !== authVersion.current) return;
      setToken(null);
      setTokenState(null);
      setUser(null);
      setRoles([]);
      throw error;
    } finally {
      if (version === authVersion.current) setLoading(false);
    }
  }

  const value: AuthCtx = {
    user,
    token: tokenState,
    loading,
    roles,
    isAdmin: roles.includes("admin"),
    signIn,
    signOut: async () => {
      authVersion.current += 1;
      setToken(null);
      setTokenState(null);
      setUser(null);
      setRoles([]);
      setLoading(false);
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
