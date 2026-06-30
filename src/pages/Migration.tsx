import { useEffect, useState } from "react";
import { ArchiveRestore, Play, RefreshCw, RotateCcw, Search } from "lucide-react";
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

  useEffect(() => {
    document.title = "Allsky migration - Sky Weaver Hub";
  }, []);

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
    try {
      const next = await SkyApi.migrationPreview({ path });
      setPreview(next);
    } catch (e: any) {
      toast.error(e.message ?? "Preview failed");
    }
  }

  async function startImport() {
    try {
      const next = await SkyApi.migrationImport({ path });
      setJob(next);
      toast.success("Import queued");
    } catch (e: any) {
      toast.error(e.message ?? "Import failed");
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
      toast.success(`Rolled back ${result.deleted_images} image(s) and ${result.deleted_products} product(s)`);
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
        <Button variant="outline" onClick={detect} disabled={detecting}><Search className="h-4 w-4 mr-2" />Detect</Button>
      </div>

      <Card className="telemetry-card space-y-4">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_auto_auto] md:items-end">
          <div className="space-y-2">
            <Label>Allsky path</Label>
            <Input value={path} onChange={(event) => setPath(event.target.value)} />
          </div>
          <Button variant="outline" onClick={runPreview}><Search className="h-4 w-4 mr-2" />Preview</Button>
          <Button onClick={startImport} disabled={!preview?.exists}><Play className="h-4 w-4 mr-2" />Queue import</Button>
        </div>
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
          {preview.unsupported_settings.length > 0 && (
            <div>
              <h3 className="text-sm font-medium">Unsupported settings</h3>
              <div className="mt-2 space-y-2">
                {preview.unsupported_settings.map((item) => (
                  <p key={item.path} className="font-mono-data text-xs text-muted-foreground truncate">{item.path} - {item.reason}</p>
                ))}
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
            <StatusBadge variant={job.status === "completed" ? "ok" : job.status === "failed" ? "error" : job.status === "running" ? "warn" : "idle"}>{job.status}</StatusBadge>
          </div>
          {job.output && (
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Stat label="images" value={String(job.output.imported_images ?? 0)} />
              <Stat label="products" value={String(job.output.imported_products ?? 0)} />
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

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-muted/20 p-3">
      <p className="text-xs uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className="mt-1 font-mono-data text-lg font-semibold">{value}</p>
    </div>
  );
}
