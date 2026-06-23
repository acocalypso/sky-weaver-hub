import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { StatusBadge } from "@/components/StatusBadge";
import { SkyApi, type SystemDiagnostics, type SystemMetrics, type SystemService } from "@/lib/api";
import { Activity, Cpu, Download, HardDrive, MemoryStick, RefreshCw, RotateCw, ServerCog, Thermometer } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { toast } from "sonner";

export default function Health() {
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [services, setServices] = useState<SystemService[]>([]);
  const [diagnostics, setDiagnostics] = useState<SystemDiagnostics | null>(null);

  useEffect(() => { document.title = "System health - Sky Weaver Hub"; load(); }, []);

  async function load() {
    try {
      const [nextMetrics, nextServices, nextDiagnostics] = await Promise.all([SkyApi.metrics(), SkyApi.systemServices(), SkyApi.diagnostics()]);
      setMetrics(nextMetrics);
      setServices(nextServices);
      setDiagnostics(nextDiagnostics);
    } catch (e: any) {
      toast.error(e.message ?? "Unable to load system health");
    }
  }

  async function restart(name: string) {
    try {
      const res = await SkyApi.restartService(name);
      toast.message(res.note ?? `${name} restart queued`);
    } catch (e: any) {
      toast.error(e.message ?? "Restart request failed");
    }
  }

  function downloadDiagnostics() {
    if (!diagnostics) return;
    const blob = new Blob([JSON.stringify(diagnostics, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `skyweaver-diagnostics-${diagnostics.generated_at.replaceAll(":", "-")}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground">Operations</p>
          <h1 className="text-3xl font-semibold tracking-tight flex items-center gap-3"><ServerCog className="h-7 w-7 text-primary" /> System health</h1>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load}><RefreshCw className="h-4 w-4 mr-2" /> Refresh</Button>
          <Button onClick={downloadDiagnostics} disabled={!diagnostics} className="bg-gradient-primary text-primary-foreground"><Download className="h-4 w-4 mr-2" /> Diagnostics JSON</Button>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <MetricCard icon={<Cpu className="h-4 w-4" />} label="CPU" value={`${(metrics?.cpu_percent ?? 0).toFixed(0)}%`} pct={metrics?.cpu_percent ?? 0} />
        <MetricCard icon={<MemoryStick className="h-4 w-4" />} label="Memory" value={`${(metrics?.memory_percent ?? 0).toFixed(0)}%`} pct={metrics?.memory_percent ?? 0} />
        <MetricCard icon={<HardDrive className="h-4 w-4" />} label="Disk" value={`${(metrics?.disk_percent ?? 0).toFixed(0)}%`} pct={metrics?.disk_percent ?? 0} />
        <MetricCard icon={<Thermometer className="h-4 w-4" />} label="Temp" value={metrics?.temperature_c ? `${metrics.temperature_c.toFixed(0)}C` : "-"} pct={metrics?.temperature_c ? (metrics.temperature_c / 85) * 100 : 0} />
        <MetricCard icon={<Activity className="h-4 w-4" />} label="Uptime" value={`${Math.floor((metrics?.uptime_seconds ?? 0) / 3600)}h`} pct={100} />
      </div>

      <Card className="telemetry-card space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Services</h2>
        {services.map((service) => (
          <div key={service.name} className="rounded-md border border-border bg-muted/20 p-3 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <p className="font-medium">{service.name}</p>
                <StatusBadge variant={serviceVariant(service.status)} pulse={service.status === "running"}>{service.status}</StatusBadge>
              </div>
              <p className="text-xs text-muted-foreground font-mono-data mt-1">
                {service.pid ? `pid ${service.pid} - ` : ""}{service.heartbeat_at ? `heartbeat ${formatDistanceToNow(new Date(service.heartbeat_at), { addSuffix: true })}` : service.managed_by ?? "-"}
              </p>
              {service.last_claimed_job_id && <p className="text-xs text-muted-foreground font-mono-data mt-1">last job {service.last_claimed_job_type} {service.last_claimed_job_id}</p>}
            </div>
            <Button variant="outline" size="sm" onClick={() => restart(service.name)}><RotateCw className="h-4 w-4 mr-2" /> Restart</Button>
          </div>
        ))}
      </Card>

      <Card className="telemetry-card grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-3">Diagnostics summary</h2>
          <dl className="grid grid-cols-2 gap-3 text-xs font-mono-data">
            <Stat k="Generated" v={diagnostics?.generated_at ? new Date(diagnostics.generated_at).toLocaleString() : "-"} />
            <Stat k="Platform" v={`${diagnostics?.platform?.system ?? "-"} ${diagnostics?.platform?.release ?? ""}`} />
            <Stat k="Python" v={diagnostics?.platform?.python ?? "-"} />
            <Stat k="DB size" v={`${Math.round((diagnostics?.database?.size_bytes ?? 0) / 1024)} KB`} />
            <Stat k="Images" v={diagnostics?.counts?.images ?? 0} />
            <Stat k="Products" v={diagnostics?.counts?.products ?? 0} />
            <Stat k="Capture queue" v={`${diagnostics?.counts?.capture_jobs_pending ?? 0} pending / ${diagnostics?.counts?.capture_jobs_running ?? 0} active`} />
            <Stat k="Processing queue" v={`${diagnostics?.counts?.processing_jobs_pending ?? 0} pending / ${diagnostics?.counts?.processing_jobs_running ?? 0} active`} />
          </dl>
        </div>
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-3">Recent log snapshot</h2>
          <div className="space-y-2 text-xs font-mono-data">
            {(diagnostics?.recent_logs ?? []).slice(0, 6).map((log, index) => (
              <div key={`${log.created_at}-${index}`} className="rounded-md bg-muted/30 p-2">
                <span className="uppercase text-muted-foreground">{log.level}</span> <span className="text-primary">{log.source}</span> {log.message}
              </div>
            ))}
            {(diagnostics?.recent_logs ?? []).length === 0 && <p className="text-sm text-muted-foreground">No recent logs.</p>}
          </div>
        </div>
      </Card>
    </div>
  );
}

function MetricCard({ icon, label, value, pct }: { icon: React.ReactNode; label: string; value: string; pct: number }) {
  return (
    <Card className="telemetry-card">
      <span className="text-[10px] uppercase tracking-widest text-muted-foreground flex items-center gap-1.5">{icon}{label}</span>
      <div className="text-2xl font-semibold font-mono-data mt-2">{value}</div>
      <Progress value={Math.max(0, Math.min(100, pct))} className="mt-3 h-1" />
    </Card>
  );
}

function Stat({ k, v }: { k: string; v: React.ReactNode }) {
  return <div className="flex flex-col gap-0.5 p-2 rounded-md bg-muted/40"><dt className="text-[10px] uppercase tracking-widest text-muted-foreground">{k}</dt><dd>{v}</dd></div>;
}

function serviceVariant(status: string): "ok" | "warn" | "error" | "idle" | "active" {
  if (status === "running") return "active";
  if (status === "stale" || status === "unknown") return "warn";
  if (status === "failed") return "error";
  return "idle";
}
