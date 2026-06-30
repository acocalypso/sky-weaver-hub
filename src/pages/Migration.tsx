import { useEffect, useState } from "react";
import { ArchiveRestore, Loader2, Play, RefreshCw, RotateCcw, Search } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StatusBadge } from "@/components/StatusBadge";
import { SkyApi, type AllskyPreview, type ProcessingJob } from "@/lib/api";

export default function Migration() {
  const [path, setPath] = useState("/home/pi/allsky");
  const [preview, setPreview] = useState<AllskyPreview | null>(null);
  const [job, setJob] = useState<ProcessingJob | null>(null);
  const [detecting, setDetecting] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [importing, setImporting] = useState(false);
  const jobId = job?.id;
  const jobStatus = job?.status;

  useEffect(() => {
    document.title = "Allsky migration - Sky Weaver Hub";
  }, []);

  useEffect(() => {
    if (!jobId || !jobStatus || !["pending", "running"].includes(jobStatus)) return;
    const timer = window.setInterval(() => {
      SkyApi.migrationJob(jobId)
        .then(setJob)
        .catch((e: any) => toast.error(e.message ?? "Job refresh failed"));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [jobId, jobStatus]);

  async function detect() {
    setDetecting(true);
    try {
      const candidates = await SkyApi.migrationDetect();
      const found = candidates.find((candidate: any) => candidate.exists);
      if (found?.path) setPath(found.path);
      toast.success(found ? "Allsky candidate found" : "No existing candidate found");
    } catch (e: any) {
      toast.error(e.message ?? "Detection failed");
    } finally {
      setDetecting(false);
    }
  }

  async function runPreview() {
    setPreviewing(true);
    try {
      const next = await SkyApi.migrationPreview({ path });
      setPreview(next);
    } catch (e: any) {
      toast.error(e.message ?? "Preview failed");
    } finally {
      setPreviewing(false);
    }
  }

  async function startImport() {
    setImporting(true);
    try {
      const next = await SkyApi.migrationImport({ path });
      setJob(next);
      toast.success("Import queued");
    } catch (e: any) {
      toast.error(e.message ?? "Import failed");
    } finally {
      setImporting(false);
    }
  }

  async function refreshJob() {
    if (!job) return;
    try {
      setJob(await SkyApi.migrationJob(job.id));
    } catch (e: any) {
      toast.error(e.message ?? "Job refresh failed");
    }
  }

  async function rollback() {
    if (!job) return;
    try {
      const result = await SkyApi.rollbackMigrationJob(job.id);
      toast.success(`Rolled back ${result.deleted_images} image(s), ${result.deleted_dark_frames ?? 0} dark frame(s), and ${result.deleted_products} product(s)`);
      await refreshJob();
    } catch (e: any) {
      toast.error(e.message ?? "Rollback failed");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground">Migration</p>
          <h1 className="text-3xl font-semibold tracking-tight flex items-center gap-3">
            <ArchiveRestore className="h-7 w-7 text-primary" /> Allsky migration
          </h1>
        </div>
        <Button variant="outline" onClick={detect} disabled={detecting}>
          {detecting ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Search className="h-4 w-4 mr-2" />}Detect
        </Button>
      </div>

      <Card className="telemetry-card space-y-4">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_auto_auto] md:items-end">
          <div className="space-y-2">
            <Label>Allsky path</Label>
            <Input value={path} onChange={(event) => setPath(event.target.value)} />
          </div>
          <Button variant="outline" onClick={runPreview} disabled={previewing}>
            {previewing ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Search className="h-4 w-4 mr-2" />}{previewing ? "Previewing" : "Preview"}
          </Button>
          <Button onClick={startImport} disabled={!preview?.exists || importing}>
            {importing ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Play className="h-4 w-4 mr-2" />}{importing ? "Queueing" : "Queue import"}
          </Button>
        </div>
        {previewing && <p className="text-xs text-muted-foreground">Scanning the Allsky tree and reading supported config files. Large installs can take a moment.</p>}
      </Card>

      {preview && (
        <Card className="telemetry-card space-y-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Preview</h2>
            <StatusBadge variant={preview.exists ? "ok" : "error"}>{preview.exists ? "found" : "missing"}</StatusBadge>
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {Object.entries(preview.counts).map(([key, value]) => <Stat key={key} label={key} value={String(value)} />)}
          </div>
          {Object.keys(preview.settings ?? {}).length > 0 && (
            <div>
              <h3 className="text-sm font-medium">Settings to apply</h3>
              <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
                {Object.entries(preview.settings).map(([key, value]) => (
                  <div key={key} className="rounded-md border border-border bg-muted/20 p-3">
                    <p className="text-xs uppercase tracking-wider text-muted-foreground">{key}</p>
                    <p className="mt-1 font-mono-data text-xs text-foreground break-words">{formatSettingValue(value)}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
          {preview.unsupported_settings.length > 0 && (
            <div>
              <h3 className="text-sm font-medium">Unsupported settings</h3>
              <div className="mt-2 max-h-48 space-y-2 overflow-auto rounded-md border border-border bg-muted/20 p-3">
                {preview.unsupported_settings.slice(0, 25).map((item, index) => (
                  <p key={`${item.path}-${item.reason}-${index}`} className="font-mono-data text-xs text-muted-foreground">
                    {item.path} - {formatUnsupported(item)}
                  </p>
                ))}
                {preview.unsupported_settings.length > 25 && <p className="text-xs text-muted-foreground">Showing first 25 unsupported setting groups.</p>}
              </div>
            </div>
          )}
          <p className="text-xs text-muted-foreground">Original Allsky files are copied, never deleted or modified.</p>
        </Card>
      )}

      {job && (
        <Card className="telemetry-card space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Import job</h2>
              <p className="font-mono-data text-xs text-muted-foreground mt-1">{job.id}</p>
            </div>
            <div className="flex items-center gap-2">
              {["pending", "running"].includes(job.status) && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
              <StatusBadge variant={job.status === "completed" ? "ok" : job.status === "failed" ? "error" : job.status === "running" ? "warn" : "idle"}>{job.status}</StatusBadge>
            </div>
          </div>
          {job.output && (
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Stat label="images" value={String(job.output.imported_images ?? 0)} />
              <Stat label="dark frames" value={String(job.output.imported_dark_frames ?? 0)} />
              <Stat label="products" value={String(job.output.imported_products ?? 0)} />
              <Stat label="overlay assets" value={String(job.output.imported_overlay_assets ?? 0)} />
              <Stat label="settings" value={String(Object.keys(job.output.settings?.applied ?? {}).length)} />
            </div>
          )}
          <div>
            <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
              <span>Progress</span>
              <span>{Math.round((job.progress ?? 0) * 100)}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <div className="h-full bg-primary transition-all" style={{ width: `${Math.round((job.progress ?? 0) * 100)}%` }} />
            </div>
          </div>
          {Array.isArray(job.output?.import_log) && job.output.import_log.length > 0 && (
            <div>
              <h3 className="text-sm font-medium">Imported file sample</h3>
              <p className="mt-1 text-xs text-muted-foreground">{formatImportSummary(job.output.import_log)}</p>
              <div className="mt-2 max-h-52 space-y-2 overflow-auto rounded-md border border-border bg-muted/20 p-3">
                {job.output.import_log.slice(0, 20).map((item: any) => (
                  <p key={`${item.kind}-${item.id}`} className="font-mono-data text-xs text-muted-foreground truncate">
                    {item.kind} {item.id} - {item.original_path}
                  </p>
                ))}
                {job.output.import_log.length > 20 && <p className="text-xs text-muted-foreground">Showing first 20 imported files.</p>}
              </div>
            </div>
          )}
          {job.error && <p className="text-sm text-destructive">{job.error}</p>}
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={refreshJob}><RefreshCw className="h-4 w-4 mr-2" />Refresh job</Button>
            <Button variant="outline" onClick={rollback} disabled={job.status !== "completed"}><RotateCcw className="h-4 w-4 mr-2" />Rollback</Button>
          </div>
        </Card>
      )}
    </div>
  );
}

function formatSettingValue(value: any) {
  if (value === null || value === undefined) return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function formatUnsupported(item: AllskyPreview["unsupported_settings"][number]) {
  if (Array.isArray(item.keys) && item.keys.length > 0) {
    const sample = item.keys.slice(0, 8).join(", ");
    return `${item.reason} (${item.count ?? item.keys.length}: ${sample}${item.keys.length > 8 ? ", ..." : ""})`;
  }
  return item.reason;
}

function formatImportSummary(items: any[]) {
  const counts = items.reduce<Record<string, number>>((acc, item) => {
    acc[item.kind] = (acc[item.kind] ?? 0) + 1;
    return acc;
  }, {});
  return Object.entries(counts).map(([kind, count]) => `${kind}: ${count}`).join(" - ");
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-muted/20 p-3">
      <p className="text-xs uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className="mt-1 font-mono-data text-lg font-semibold">{value}</p>
    </div>
  );
}
