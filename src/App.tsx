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
const ImageDetail = lazy(() => import("@/pages/ImageDetail"));
const Timelapses = lazy(() => import("@/pages/Timelapses"));
const Health = lazy(() => import("@/pages/Health"));
const Logs = lazy(() => import("@/pages/Logs"));
const SettingsPage = lazy(() => import("@/pages/Settings"));
const ApiKeys = lazy(() => import("@/pages/ApiKeys"));
const DeveloperApi = lazy(() => import("@/pages/DeveloperApi"));
const Modules = lazy(() => import("@/pages/Modules"));
const RemoteUpload = lazy(() => import("@/pages/RemoteUpload"));
const Migration = lazy(() => import("@/pages/Migration"));
const Setup = lazy(() => import("@/pages/Setup"));
const PublicSky = lazy(() => import("@/pages/PublicSky"));
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
              <Route path="/public" element={<PublicSky />} />
              <Route path="/auth" element={<AuthPage />} />
              <Route path="/setup" element={<ProtectedRoute><Setup /></ProtectedRoute>} />
              <Route element={<ProtectedRoute><AppShell /></ProtectedRoute>}>
                <Route path="/" element={<Dashboard />} />
                <Route path="/cameras" element={<Cameras />} />
                <Route path="/schedule" element={<Schedule />} />
                <Route path="/gallery" element={<Gallery />} />
                <Route path="/gallery/:imageId" element={<ImageDetail />} />
                <Route path="/timelapses" element={<Timelapses />} />
                <Route path="/health" element={<Health />} />
                <Route path="/logs" element={<Logs />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="/api-keys" element={<ApiKeys />} />
                <Route path="/developer" element={<DeveloperApi />} />
                <Route path="/modules" element={<Modules />} />
                <Route path="/remote-upload" element={<RemoteUpload />} />
                <Route path="/migration" element={<Migration />} />
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
