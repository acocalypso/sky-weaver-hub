import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/hooks/auth-context";
import { SkyApi } from "@/lib/api";
import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading, isAdmin } = useAuth();
  const location = useLocation();
  const [setupRequired, setSetupRequired] = useState<boolean | null>(null);
  const [setupError, setSetupError] = useState(false);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let alive = true;
    setSetupError(false);
    if (!user) {
      setSetupRequired(null);
      return;
    }
    if (!isAdmin) {
      setSetupRequired(false);
      return;
    }
    setSetupRequired(null);
    SkyApi.setupStatus()
      .then((status) => { if (alive) setSetupRequired(status.required); })
      .catch(() => { if (alive) setSetupError(true); });
    return () => { alive = false; };
  }, [user, isAdmin, location.pathname, retry]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }
  if (!user) return <Navigate to="/auth" replace />;
  if (setupError) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4">
        <p role="alert">Unable to verify setup status.</p>
        <button type="button" className="rounded-md border px-4 py-2" onClick={() => setRetry((value) => value + 1)}>Retry</button>
      </div>
    );
  }
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
