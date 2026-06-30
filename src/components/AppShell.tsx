import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, Camera, CalendarClock, Images, Film, ScrollText,
  Settings, KeyRound, Code2, ServerCog, LogOut, Telescope, Menu, X, Activity,
  Puzzle, CloudUpload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/auth-context";
import { Starfield } from "@/components/Starfield";
import { useState } from "react";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/cameras", label: "Cameras", icon: Camera },
  { to: "/schedule", label: "Schedule", icon: CalendarClock },
  { to: "/gallery", label: "Gallery", icon: Images },
  { to: "/timelapses", label: "Timelapses", icon: Film },
  { to: "/health", label: "Health", icon: Activity },
  { to: "/logs", label: "Logs", icon: ScrollText },
  { to: "/settings", label: "Settings", icon: Settings },
  { to: "/api-keys", label: "API Keys", icon: KeyRound },
  { to: "/developer", label: "Developer API", icon: Code2 },
  { to: "/modules", label: "Modules", icon: Puzzle },
  { to: "/remote-upload", label: "Remote Upload", icon: CloudUpload },
  { to: "/deployment", label: "Deployment", icon: ServerCog },
];

export function AppShell() {
  const { user, signOut, isAdmin } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const handleSignOut = async () => {
    await signOut();
    navigate("/auth");
  };

  return (
    <div className="relative min-h-screen flex">
      <Starfield />

      {/* Sidebar */}
      <aside
        className={cn(
          "fixed lg:static inset-y-0 left-0 z-40 w-64 shrink-0 bg-sidebar border-r border-sidebar-border flex flex-col transition-transform",
          open ? "translate-x-0" : "-translate-x-full lg:translate-x-0",
        )}
      >
        <div className="h-16 flex items-center gap-2 px-5 border-b border-sidebar-border">
          <div className="h-8 w-8 rounded-md bg-gradient-primary flex items-center justify-center glow-primary">
            <Telescope className="h-4 w-4 text-primary-foreground" />
          </div>
          <div className="flex flex-col leading-tight">
            <span className="text-sm font-semibold text-sidebar-foreground">Sky Weaver Hub</span>
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Observatory Hub</span>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto p-3 space-y-0.5">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors",
                  isActive
                    ? "bg-sidebar-accent text-sidebar-accent-foreground border-l-2 border-primary"
                    : "text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
                )
              }
            >
              <n.icon className="h-4 w-4" />
              {n.label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-sidebar-border p-3">
          <div className="px-2 py-2 text-xs">
            <div className="text-sidebar-foreground truncate">{user?.username}</div>
            <div className="text-muted-foreground flex items-center gap-1.5 mt-1">
              <span className="status-dot text-status-ok" />
              {isAdmin ? "Admin" : "Viewer"}
            </div>
          </div>
          <Button variant="ghost" size="sm" className="w-full justify-start" onClick={handleSignOut}>
            <LogOut className="h-4 w-4 mr-2" /> Sign out
          </Button>
        </div>
      </aside>

      {/* Mobile overlay */}
      {open && (
        <div className="fixed inset-0 z-30 bg-background/80 lg:hidden" onClick={() => setOpen(false)} />
      )}

      {/* Main */}
      <div className="flex-1 min-w-0 flex flex-col relative z-10">
        <header className="h-16 lg:hidden flex items-center justify-between px-4 border-b border-border bg-background/80 backdrop-blur sticky top-0 z-20">
          <Button variant="ghost" size="icon" onClick={() => setOpen(!open)}>
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </Button>
          <div className="flex items-center gap-2">
            <Telescope className="h-4 w-4 text-primary" />
            <span className="text-sm font-semibold">Sky Weaver Hub</span>
          </div>
          <div className="w-9" />
        </header>
        <main className="flex-1 p-4 lg:p-8 max-w-[1600px] mx-auto w-full animate-fade-in">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
