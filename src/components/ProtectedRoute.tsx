import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/hooks/auth-context";
import { SkyApi } from "@/lib/api";
import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  const [setupRequired, setSetupRequired] = useState<boolean | null>(null);

  useEffect(() => {
    let alive = true;
    if (!user) {
      setSetupRequired(null);
      return;
    }
    SkyApi.setupStatus()
      .then((status) => { if (alive) setSetupRequired(status.required); })
      .catch(() => { if (alive) setSetupRequired(false); });
    return () => { alive = false; };
  }, [user, location.pathname]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }
  if (!user) return <Navigate to="/auth" replace />;
  if (setupRequired === null) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }
  if (setupRequired && location.pathname !== "/setup") return <Navigate to="/setup" replace />;
  if (!setupRequired && location.pathname === "/setup") return <Navigate to="/" replace />;
  return <>{children}</>;
}
