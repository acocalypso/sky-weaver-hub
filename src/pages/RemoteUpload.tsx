import { useEffect, useId, useState } from "react";
import { CloudUpload, FolderSync, Loader2, RefreshCw, Send, TestTube2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { SkyApi, type RemoteTarget, type RemoteTargetType, type UploadJob } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export default function RemoteUpload() {
  const [targets, setTargets] = useState<RemoteTarget[]>([]);
  const [jobs, setJobs] = useState<UploadJob[]>([]);
  const [selectedJob, setSelectedJob] = useState<UploadJob | null>(null);
  const [name, setName] = useState("Local mirror");
  const [targetType, setTargetType] = useState<RemoteTargetType>("filesystem");
  const [destination, setDestination] = useState("");
  const [host, setHost] = useState("");
  const [username, setUsername] = useState("pi");
  const [remotePath, setRemotePath] = useState("/var/www/html/allsky");
  const [port, setPort] = useState("22");
  const [sshKeyPath, setSshKeyPath] = useState("");
  const [password, setPassword] = useState("");
  const [passive, setPassive] = useState(true);
  const [enabled, setEnabled] = useState(true);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [selectedJobLoading, setSelectedJobLoading] = useState<string | null>(null);

  useEffect(() => {
    document.title = "Remote upload - Sky Weaver Hub";
    let ignore = false;
    void load({ shouldUpdate: () => !ignore });
    return () => {
      ignore = true;
    };
  }, []);

  async function load(options: { quiet?: boolean; shouldUpdate?: () => boolean } = {}) {
    if (!options.quiet) setLoading(true);
    setLoadError(null);
    try {
      const [nextTargets, nextJobs] = await Promise.all([SkyApi.remoteTargets(), SkyApi.uploadJobs()]);
      if (options.shouldUpdate && !options.shouldUpdate()) return;
      setTargets(nextTargets);
      setJobs(nextJobs);
    } catch (e: any) {
      if (options.shouldUpdate && !options.shouldUpdate()) return;
      const message = e.message ?? "Remote upload load failed";
      setLoadError(message);
      toast.error(message);
    } finally {
      if (!options.shouldUpdate || options.shouldUpdate()) setLoading(false);
    }
  }

  async function addTarget() {
    if (!canAddTarget) return;
    setPendingAction("add-target");
    try {
      const config = targetType === "filesystem"
        ? { destination_path: destination }
        : isSshTarget(targetType)
          ? { host, username, remote_path: remotePath, port: Number(port || 22), ssh_key_path: sshKeyPath || undefined }
          : { host, username, password, remote_path: remotePath, port: Number(port || 21), passive };
      const target = await SkyApi.createRemoteTarget({ name, type: targetType, enabled, config });
      setTargets([target, ...targets]);
      toast.success("Remote target saved");
    } catch (e: any) {
      toast.error(e.message ?? "Create target failed");
    } finally {
      setPendingAction(null);
    }
  }

  async function toggleTarget(target: RemoteTarget, nextEnabled: boolean) {
    const action = `toggle:${target.id}`;
    setPendingAction(action);
    try {
      const updated = await SkyApi.patchRemoteTarget(target.id, { name: target.name, type: target.type as RemoteTargetType, enabled: nextEnabled });
      setTargets(targets.map((item) => (item.id === target.id ? updated : item)));
    } catch (e: any) {
      toast.error(e.message ?? "Update target failed");
    } finally {
      setPendingAction(null);
    }
  }

  async function testTarget(target: RemoteTarget) {
    const action = `test:${target.id}`;
    setPendingAction(action);
    try {
      const result = await SkyApi.testRemoteTarget(target.id);
      toast.success(`Target ${result.status}`);
    } catch (e: any) {
      toast.error(e.message ?? "Target test failed");
    } finally {
      setPendingAction(null);
    }
  }

  async function queueLatest(target?: RemoteTarget) {
    const action = target ? `queue:${target.id}` : "queue:latest";
    setPendingAction(action);
    try {
      await SkyApi.queueUpload({ source_type: "latest", target_id: target?.id });
      toast.success("Upload queued");
      await load({ quiet: true });
    } catch (e: any) {
      toast.error(e.message ?? "Queue upload failed");
    } finally {
      setPendingAction(null);
    }
  }

  async function retryFailed() {
    setPendingAction("retry");
    try {
      const result = await SkyApi.retryUploads();
      toast.success(result.upload_job_ids.length ? "Retry queued" : "No failed uploads");
      await load({ quiet: true });
    } catch (e: any) {
      toast.error(e.message ?? "Retry failed");
    } finally {
      setPendingAction(null);
    }
  }

  async function showJob(job: UploadJob) {
    setSelectedJobLoading(job.id);
    try {
      setSelectedJob(await SkyApi.uploadJob(job.id));
    } catch (e: any) {
      toast.error(e.message ?? "Upload job detail failed");
    } finally {
      setSelectedJobLoading(null);
    }
  }

  const failedJobs = jobs.filter((job) => job.status === "failed").length;
  const activeJobs = jobs.filter((job) => ["pending", "running"].includes(job.status)).length;
  const enabledTargets = targets.filter((target) => target.enabled).length;
  const validPort = Number.isInteger(Number(port)) && Number(port) > 0 && Number(port) <= 65535;
  const canAddTarget = Boolean(
    name.trim()
    && validPort
    && (targetType === "filesystem" ? destination.trim() : host.trim() && username.trim() && remotePath.trim())
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground">Operations</p>
          <h1 className="text-3xl font-semibold tracking-tight flex items-center gap-3">
            <CloudUpload className="h-7 w-7 text-primary" /> Remote upload
          </h1>
        </div>
        <div className="grid grid-cols-1 gap-2 min-[420px]:grid-cols-3 sm:flex sm:flex-wrap sm:justify-end">
          <Button variant="outline" onClick={() => load()} disabled={loading} className="w-full sm:w-auto">
            {loading ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <RefreshCw className="h-4 w-4 mr-2" />}Refresh
          </Button>
          <Button variant="outline" onClick={retryFailed} disabled={pendingAction === "retry"} className="w-full sm:w-auto">
            {pendingAction === "retry" ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <FolderSync className="h-4 w-4 mr-2" />}Retry failed
          </Button>
          <Button onClick={() => queueLatest()} disabled={pendingAction === "queue:latest"} className="w-full sm:w-auto">
            {pendingAction === "queue:latest" ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Send className="h-4 w-4 mr-2" />}Queue latest
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Summary label="Targets" value={String(targets.length)} />
        <Summary label="Enabled" value={String(enabledTargets)} />
        <Summary label="Active jobs" value={String(activeJobs)} />
        <Summary label="Failed jobs" value={String(failedJobs)} tone={failedJobs ? "error" : "default"} />
      </div>

      {(loading || loadError) && (
        <Card className="telemetry-card flex items-center gap-3 text-sm text-muted-foreground">
          {loading && <Loader2 className="h-4 w-4 animate-spin text-primary" />}
          <span>{loading ? "Loading remote targets and upload jobs" : loadError}</span>
        </Card>
      )}

      <Card className="telemetry-card space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Upload target</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_1fr_auto] md:items-end">
          <Field label="Name" value={name} onChange={setName} />
          <div className="space-y-2">
            <Label>Type</Label>
            <select className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={targetType} onChange={(event) => setTargetType(event.target.value as RemoteTargetType)}>
              <option value="filesystem">Filesystem</option>
              <option value="rsync_ssh">Rsync over SSH</option>
              <option value="scp_ssh">SCP over SSH</option>
              <option value="sftp_ssh">SFTP over SSH</option>
              <option value="ftp">FTP</option>
              <option value="ftps">FTPS</option>
            </select>
          </div>
          <div className="flex items-center gap-3 pb-2">
            <Switch checked={enabled} onCheckedChange={setEnabled} />
            <span className="text-sm text-muted-foreground">Enabled</span>
          </div>
        </div>
        {targetType === "filesystem" ? (
          <Field label="Destination path" value={destination} onChange={setDestination} placeholder="/mnt/allsky-upload" />
        ) : isSshTarget(targetType) ? (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
            <Field label="Host" value={host} onChange={setHost} placeholder="example.local" />
            <Field label="Username" value={username} onChange={setUsername} />
            <Field label="Remote path" value={remotePath} onChange={setRemotePath} />
            <Field label="Port" value={port} onChange={setPort} type="number" min={1} max={65535} />
            <Field label="SSH key path" value={sshKeyPath} onChange={setSshKeyPath} placeholder="/home/skyweaver/.ssh/id_ed25519" />
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
            <Field label="Host" value={host} onChange={setHost} placeholder="ftp.example.com" />
            <Field label="Username" value={username} onChange={setUsername} />
            <Field label="Password" value={password} onChange={setPassword} type="password" />
            <Field label="Remote path" value={remotePath} onChange={setRemotePath} />
            <Field label="Port" value={port} onChange={setPort} type="number" min={1} max={65535} />
            <div className="flex items-center gap-3 pb-2 md:col-span-2 xl:col-span-1">
              <Switch checked={passive} onCheckedChange={setPassive} />
              <span className="text-sm text-muted-foreground">Passive mode</span>
            </div>
          </div>
        )}
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-muted-foreground">{canAddTarget ? "Target configuration is ready to save." : "Enter the required target details before saving."}</p>
          <Button onClick={addTarget} disabled={!canAddTarget || pendingAction === "add-target"} className="w-full sm:w-auto">
            {pendingAction === "add-target" && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            Add target
          </Button>
        </div>
      </Card>

      <Card className="telemetry-card space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Targets</h2>
        {targets.map((target) => (
          <div key={target.id} className="rounded-md border border-border bg-muted/20 p-3 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <p className="font-medium truncate">{target.name}</p>
                <StatusBadge variant={target.enabled ? "ok" : "idle"}>{target.enabled ? "enabled" : "disabled"}</StatusBadge>
              </div>
              <p className="mt-1 font-mono-data text-xs text-muted-foreground truncate">{target.type} - {formatTargetDestination(target)}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={() => testTarget(target)} disabled={pendingAction === `test:${target.id}`}>
                {pendingAction === `test:${target.id}` ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <TestTube2 className="h-4 w-4 mr-2" />}Test
              </Button>
              <Button variant="outline" size="sm" onClick={() => queueLatest(target)} disabled={pendingAction === `queue:${target.id}`}>
                {pendingAction === `queue:${target.id}` ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Send className="h-4 w-4 mr-2" />}Queue latest
              </Button>
              <Button variant="outline" size="sm" onClick={() => toggleTarget(target, !target.enabled)} disabled={pendingAction === `toggle:${target.id}`}>
                {pendingAction === `toggle:${target.id}` && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                {target.enabled ? "Disable" : "Enable"}
              </Button>
            </div>
          </div>
        ))}
        {targets.length === 0 && <p className="text-sm text-muted-foreground">No upload targets configured.</p>}
      </Card>

      <Card className="telemetry-card space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Upload jobs</h2>
        {jobs.map((job) => (
          <div key={job.id} className="rounded-md border border-border bg-muted/20 p-3">
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-medium">{job.source_type} {job.source_id}</p>
              <StatusBadge variant={job.status === "completed" ? "ok" : job.status === "failed" ? "error" : job.status === "running" ? "warn" : "idle"}>{job.status}</StatusBadge>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{job.target_name ?? job.target_id} {job.target_type ? `(${job.target_type})` : ""} - attempts {job.attempts}</p>
            <p className="mt-1 font-mono-data text-xs text-muted-foreground truncate">{job.destination_path ?? job.source_path}</p>
            {job.last_error && <p className="mt-2 text-xs text-destructive">{job.last_error}</p>}
            <Button className="mt-3" variant="outline" size="sm" onClick={() => showJob(job)} disabled={selectedJobLoading === job.id}>
              {selectedJobLoading === job.id && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Details
            </Button>
          </div>
        ))}
        {jobs.length === 0 && <p className="text-sm text-muted-foreground">No upload jobs yet.</p>}
      </Card>

      {selectedJob && (
        <Card className="telemetry-card space-y-3">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Job detail</h2>
            <StatusBadge variant={selectedJob.status === "completed" ? "ok" : selectedJob.status === "failed" ? "error" : selectedJob.status === "running" ? "warn" : "idle"}>{selectedJob.status}</StatusBadge>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <Detail label="Target" value={`${selectedJob.target_name ?? selectedJob.target_id}${selectedJob.target_type ? ` (${selectedJob.target_type})` : ""}`} />
            <Detail label="Attempts" value={String(selectedJob.attempts)} />
            <Detail label="Processing job" value={selectedJob.processing_job_id ?? "-"} />
            <Detail label="Created" value={formatDate(selectedJob.created_at)} />
            <Detail label="Started" value={formatDate(selectedJob.started_at)} />
            <Detail label="Completed" value={formatDate(selectedJob.completed_at)} />
          </div>
          <Detail label="Source" value={selectedJob.source_path} />
          <Detail label="Destination" value={selectedJob.destination_path ?? "-"} />
          {selectedJob.last_error && <p className="text-sm text-destructive">{selectedJob.last_error}</p>}
        </Card>
      )}
    </div>
  );
}

function formatTargetDestination(target: RemoteTarget) {
  if (target.type === "rsync_ssh" || target.type === "scp_ssh" || target.type === "sftp_ssh" || target.type === "ftp" || target.type === "ftps") {
    return `${target.config.username}@${target.config.host}:${target.config.remote_path}`;
  }
  return target.config.destination_path ?? "-";
}

function isSshTarget(type: RemoteTargetType) {
  return type === "rsync_ssh" || type === "scp_ssh" || type === "sftp_ssh";
}

function formatDate(value?: string | null) {
  return value ? new Date(value).toLocaleString() : "-";
}

function Summary({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "error" }) {
  return (
    <div className="rounded-md border border-border bg-muted/20 p-3" data-testid={`remote-summary-${label.toLowerCase().replaceAll(" ", "-")}`}>
      <p className="text-xs uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className={`mt-1 font-mono-data text-xl font-semibold ${tone === "error" ? "text-destructive" : ""}`}>{value}</p>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border border-border bg-muted/20 p-3">
      <p className="text-xs uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className="mt-1 truncate font-mono-data text-xs">{value}</p>
    </div>
  );
}

function Field({ label, value, onChange, ...rest }: { label: string; value: string; onChange: (value: string) => void } & React.InputHTMLAttributes<HTMLInputElement>) {
  const generatedId = useId();
  const inputId = rest.id ?? generatedId;
  return (
    <div className="space-y-2">
      <Label htmlFor={inputId}>{label}</Label>
      <Input id={inputId} value={value} onChange={(event) => onChange(event.target.value)} {...rest} />
    </div>
  );
}
