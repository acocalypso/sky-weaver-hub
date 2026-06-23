import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/hooks/useAuth";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { AppShell } from "@/components/AppShell";
import Dashboard from "@/pages/Dashboard";
import AuthPage from "@/pages/Auth";
import NotFound from "@/pages/NotFound";
import Cameras from "@/pages/Cameras";
import Schedule from "@/pages/Schedule";
import Gallery from "@/pages/Gallery";
import Timelapses from "@/pages/Timelapses";
import Logs from "@/pages/Logs";
import SettingsPage from "@/pages/Settings";
import ApiKeys from "@/pages/ApiKeys";
import DeveloperApi from "@/pages/DeveloperApi";
import { Deployment } from "@/pages/Placeholder";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner position="top-right" theme="dark" />
      <BrowserRouter>
        <AuthProvider>
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
        </AuthProvider>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
