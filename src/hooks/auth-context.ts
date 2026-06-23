import { createContext, useContext } from "react";
import { type SkyUserPrincipal } from "@/lib/api";

export type Role = "admin" | "operator" | "viewer";

export interface AuthCtx {
  user: SkyUserPrincipal | null;
  token: string | null;
  loading: boolean;
  roles: Role[];
  isAdmin: boolean;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

export const AuthContext = createContext<AuthCtx | undefined>(undefined);

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
