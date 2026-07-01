import { Card } from "@/components/ui/card";
import { Construction } from "lucide-react";

export function Placeholder({ title, description }: { title: string; description: string }) {
  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-widest text-muted-foreground">Module</p>
        <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
      </div>
      <Card className="telemetry-card flex items-start gap-4">
        <div className="h-10 w-10 rounded-md bg-accent/10 border border-accent/30 flex items-center justify-center shrink-0">
          <Construction className="h-5 w-5 text-accent" />
        </div>
        <div>
          <p className="text-sm font-medium">Planned operational page</p>
          <p className="text-sm text-muted-foreground mt-1">{description}</p>
        </div>
      </Card>
    </div>
  );
}

export const Cameras = () => <Placeholder title="Cameras" description="Manage camera profiles, adapter types (mock / libcamera / gphoto2 / INDI / ZWO / webcam / custom), and per-camera settings." />;
export const Schedule = () => <Placeholder title="Schedule" description="Configure night automation: sun-altitude triggers, twilight conditions, interval, exposure ramping, weather-safe flags." />;
export const Gallery = () => <Placeholder title="Gallery" description="Date picker, filters by event type and quality, image detail with full metadata and API response preview." />;
export const Timelapses = () => <Placeholder title="Timelapses" description="Create timelapse jobs, watch a queue view (pending → running → complete), and download outputs." />;
export const Logs = () => <Placeholder title="Logs & diagnostics" description="Structured logs filterable by level and source, plus diagnostic export and service status panel." />;
export const Settings = () => <Placeholder title="Settings" description="Location, storage paths, capture interval, retention policy, API and security settings, startup behavior." />;
export const ApiKeys = () => <Placeholder title="API Keys" description="Create, name, and revoke API keys for external apps. Assign scopes (read:status, read:images, write:capture, write:settings, admin)." />;
export const DeveloperApi = () => <Placeholder title="Developer API" description="Interactive REST API reference with curl, JavaScript and Python examples, plus realtime event docs." />;
export const Deployment = () => <Placeholder title="Deployment" description="Raspberry Pi & Linux setup guide: required packages, systemd service, env vars, Nginx + HTTPS, camera adapter wiring." />;
