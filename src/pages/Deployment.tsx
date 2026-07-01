import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/StatusBadge";
import { ExternalLink, HardDrive, ServerCog, ShieldCheck, Terminal } from "lucide-react";

const paths = [
  ["/opt/skyweaver", "application code"],
  ["/etc/skyweaver/skyweaver.env", "local configuration"],
  ["/var/lib/skyweaver", "database, images, web build"],
  ["/var/log/skyweaver", "service logs"],
];

const services = [
  ["skyweaver.target", "starts the full stack"],
  ["skyweaver-api.service", "REST API and WebUI"],
  ["skyweaver-capture.service", "camera capture daemon"],
  ["skyweaver-worker.service", "processing and upload worker"],
];

const commands = [
  ["Install", "sudo ./install.sh"],
  ["Upgrade", "git pull --ff-only && sudo ./upgrade.sh"],
  ["Status", "systemctl status skyweaver.target"],
  ["Logs", "journalctl -u skyweaver-api.service -u skyweaver-capture.service -u skyweaver-worker.service -f"],
  ["Support bundle", "sudo ./support.sh"],
];

const checks = [
  "Installer preserves existing config, database, images, and logs.",
  "Upgrade skips backend pip install when requirements are unchanged and the venv exists.",
  "ZWO setup installs libasi and USB rules only when the ZWO adapter is configured or explicitly requested.",
  "Service-control sudoers entries are limited to Sky Weaver systemd units.",
];

export default function Deployment() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground">Operations</p>
          <h1 className="flex items-center gap-3 text-3xl font-semibold tracking-tight">
            <ServerCog className="h-7 w-7 text-primary" /> Deployment
          </h1>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusBadge variant="active">local first</StatusBadge>
          <StatusBadge variant="ok">systemd</StatusBadge>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <Card className="telemetry-card space-y-4">
          <div className="flex items-center gap-3">
            <Terminal className="h-5 w-5 text-primary" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Operator commands</h2>
          </div>
          <div className="space-y-3">
            {commands.map(([label, command]) => (
              <div key={label} className="grid grid-cols-1 gap-2 rounded-md bg-muted/30 p-3 md:grid-cols-[120px_1fr] md:items-center">
                <span className="text-sm font-medium">{label}</span>
                <code className="overflow-auto rounded bg-background/70 px-2 py-1 text-xs font-mono-data">{command}</code>
              </div>
            ))}
          </div>
        </Card>

        <Card className="telemetry-card space-y-4">
          <div className="flex items-center gap-3">
            <ShieldCheck className="h-5 w-5 text-primary" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Upgrade behavior</h2>
          </div>
          <div className="space-y-3">
            {checks.map((check) => (
              <div key={check} className="rounded-md border border-border bg-muted/20 p-3 text-sm text-muted-foreground">
                {check}
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="telemetry-card space-y-4">
          <div className="flex items-center gap-3">
            <HardDrive className="h-5 w-5 text-primary" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Installed paths</h2>
          </div>
          <div className="divide-y divide-border/60">
            {paths.map(([path, purpose]) => (
              <div key={path} className="grid grid-cols-1 gap-1 py-3 sm:grid-cols-[1fr_180px] sm:items-center">
                <code className="break-all text-xs font-mono-data">{path}</code>
                <span className="text-sm text-muted-foreground">{purpose}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card className="telemetry-card space-y-4">
          <div className="flex items-center gap-3">
            <ServerCog className="h-5 w-5 text-primary" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Systemd units</h2>
          </div>
          <div className="divide-y divide-border/60">
            {services.map(([service, purpose]) => (
              <div key={service} className="grid grid-cols-1 gap-1 py-3 sm:grid-cols-[1fr_220px] sm:items-center">
                <code className="text-xs font-mono-data">{service}</code>
                <span className="text-sm text-muted-foreground">{purpose}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card className="telemetry-card flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Full docs</h2>
          <p className="mt-1 text-sm text-muted-foreground">Detailed install, upgrade, Raspberry Pi, troubleshooting, and uninstall notes are kept in the repository docs.</p>
        </div>
        <Button asChild variant="outline">
          <a href="https://github.com/acocalypso/sky-weaver-hub/tree/main/docs" target="_blank" rel="noreferrer">
            Open docs <ExternalLink className="ml-2 h-4 w-4" />
          </a>
        </Button>
      </Card>
    </div>
  );
}
