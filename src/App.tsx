import { lazy, Suspense } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/hooks/useAuth";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { AppShell } from "@/components/AppShell";

const Dashboard = lazy(() => import("@/pages/Dashboard"));
const AuthPage = lazy(() => import("@/pages/Auth"));
const NotFound = lazy(() => import("@/pages/NotFound"));
const Cameras = lazy(() => import("@/pages/Cameras"));
const Schedule = lazy(() => import("@/pages/Schedule"));
const Gallery = lazy(() => import("@/pages/Gallery"));
const Timelapses = lazy(() => import("@/pages/Timelapses"));
const Logs = lazy(() => import("@/pages/Logs"));
const SettingsPage = lazy(() => import("@/pages/Settings"));
const ApiKeys = lazy(() => import("@/pages/ApiKeys"));
const DeveloperApi = lazy(() => import("@/pages/DeveloperApi"));
const Deployment = lazy(() => import("@/pages/Placeholder").then((module) => ({ default: module.Deployment })));

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner position="top-right" theme="dark" />
      <BrowserRouter>
        <AuthProvider>
          <Suspense fallback={<RouteLoading />}>
            <Routes>
              <Route path="/auth" element={<AuthPage />} />
              <Route element={<ProtectedRoute><AppShell /></ProtectedRoute>}>
                <Route path="/" element={<Dashboard />} />
                <Route path="/cameras" element={<Cameras />} />
                <Route path="/schedule" element={<Schedule />} />
                <Route path="/gallery" element={<Gallery />} />
                <Route path="/timelapses" element={<Timelapses />} />
                <Route path="/logs" element={<Logs />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="/api-keys" element={<ApiKeys />} />
                <Route path="/developer" element={<DeveloperApi />} />
                <Route path="/deployment" element={<Deployment />} />
              </Route>
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Suspense>
        </AuthProvider>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

function RouteLoading() {
  return <div className="min-h-screen bg-background text-foreground" />;
}

export default App;
