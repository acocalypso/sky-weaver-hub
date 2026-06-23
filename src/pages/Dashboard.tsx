import { useEffect, useMemo, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { StatusBadge } from "@/components/StatusBadge";
import { SkyApi, type CameraRow, type CaptureJob, type ImageRow, type SchedulePreview, type SkyStatus, type SystemMetrics } from "@/lib/api";
import { getTonightTimeline, getSunAltitude } from "@/lib/sun";
import sampleSky from "@/assets/sample-sky-1.jpg";
import { Play, Pause, Square, Camera, RefreshCw, Film, RotateCw, Cpu, MemoryStick, HardDrive, Thermometer, Activity, Clock } from "lucide-react";
import { toast } from "sonner";
import { format, formatDistanceToNow } from "date-fns";

export default function Dashboard() {
  const [status, setStatus] = useState<SkyStatus | null>(null);
  const [images, setImages] = useState<ImageRow[]>([]);
  const [settings, setSettings] = useState<any>(null);
  const [metrics, setMetrics] = useState<SystemMetrics>({ cpu_percent: 0, memory_percent: 0, disk_percent: 0, disk_free_gb: 0, temperature_c: null, uptime_seconds: 0 });
  const [schedulePreview, setSchedulePreview] = useState<SchedulePreview | null>(null);
  const [captureJobs, setCaptureJobs] = useState<CaptureJob[]>([]);
  const [sequenceForm, setSequenceForm] = useState({ count: 5, delay_seconds: 2, exposure_ms: 1000, gain: 1 });

  useEffect(() => { document.title = "Dashboard - Sky Weaver Hub"; }, []);
  useEffect(() => {
    load();
    const t = setInterval(loadLight, 5000);
    return () => clearInterval(t);
  }, []);

  async function load() {
    try {
      const [st, imgs, sets, m, sched, jobs] = await Promise.all([SkyApi.status(), SkyApi.images("?limit=8"), SkyApi.settings(), SkyApi.metrics(), SkyApi.schedulePreview(), SkyApi.captureJobs()]);
      setStatus(st); setImages(imgs); setSettings(sets); setMetrics(m); setSchedulePreview(sched); setCaptureJobs(jobs.slice(0, 6));
    } catch (e: any) {
      toast.error(e.message ?? "Unable to load dashboard");
    }
  }

  async function loadLight() {
    try {
      const [st, imgs, m, sched, jobs] = await Promise.all([SkyApi.status(), SkyApi.images("?limit=8"), SkyApi.metrics(), SkyApi.schedulePreview(), SkyApi.captureJobs()]);
      setStatus(st); setImages(imgs); setMetrics(m); setSchedulePreview(sched); setCaptureJobs(jobs.slice(0, 6));
    } catch {
      // Keep the last visible telemetry during transient API restarts.
    }
  }

  const observatory = settings?.observatory ?? { name: "Sky Weaver Observatory", latitude: 0, longitude: 0, timezone: "UTC" };
  const camera = status?.camera as CameraRow | null;
  const latest = images[0] ?? status?.latest_image;
  const captureStatus = status?.capture?.status ?? "idle";
  const latitude = Number(observatory.latitude);
  const longitude = Number(observatory.longitude);
  const validLocation = Number.isFinite(latitude) && Number.isFinite(longitude);

  const timeline = useMemo(() => getTonightTimeline(validLocation ? latitude : 0, validLocation ? longitude : 0), [latitude, longitude, validLocation]);
  const sunAlt = useMemo(() => validLocation ? getSunAltitude(latitude, longitude) : null, [latitude, longitude, validLocation]);

  async function quickAction(type: string) {
    try {
      if (type === "start") await SkyApi.captureStart();
      if (type === "pause") await SkyApi.capturePause();
      if (type === "resume") await SkyApi.captureResume();
      if (type === "stop") await SkyApi.captureStop();
      if (type === "test") await SkyApi.testShot({ camera_id: camera?.id, exposure_ms: 1000, gain: 1, mode: "manual" });
      if (type === "single") await SkyApi.queueSingleCapture({ camera_id: camera?.id, exposure_ms: sequenceForm.exposure_ms, gain: sequenceForm.gain, mode: "manual" });
      if (type === "timelapse") await SkyApi.createProduct("timelapse", { day_key: latest?.day_key });
      toast.success(type === "test" ? "Test shot captured" : type === "single" ? "Single capture queued" : "Command accepted");
      await load();
    } catch (e: any) {
      toast.error(e.message ?? "Command failed");
    }
  }

  async function queueSequence() {
    try {
      const job = await SkyApi.queueSequenceCapture({
        count: sequenceForm.count,
        delay_seconds: sequenceForm.delay_seconds,
        capture: { camera_id: camera?.id, exposure_ms: sequenceForm.exposure_ms, gain: sequenceForm.gain, mode: "sequence" },
      });
      setCaptureJobs([{ ...job, request: { ...sequenceForm }, progress: job.progress ?? 0 }, ...captureJobs].slice(0, 6));
      toast.success("Sequence queued");
      await load();
    } catch (e: any) {
      toast.error(e.message ?? "Sequence queue failed");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground">Observatory</p>
          <h1 className="text-3xl font-semibold tracking-tight">{observatory.name}</h1>
          <p className="text-sm text-muted-foreground mt-1 font-mono-data">
            {formatCoordinate(latitude)} deg, {formatCoordinate(longitude)} deg - Sun alt {typeof sunAlt === "number" && Number.isFinite(sunAlt) ? `${sunAlt.toFixed(1)} deg` : "-"}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <StatusBadge variant={captureStatus === "running" ? "active" : captureStatus === "error" ? "error" : "idle"} pulse={captureStatus === "running"}>{captureStatus}</StatusBadge>
          <StatusBadge variant={camera?.enabled ? "ok" : "error"}>{camera?.adapter ?? "no camera"}</StatusBadge>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button onClick={() => quickAction("start")} className="bg-gradient-primary text-primary-foreground hover:opacity-90"><Play className="h-4 w-4 mr-2" /> Start capture</Button>
        {captureStatus === "paused" ? (
          <Button variant="outline" onClick={() => quickAction("resume")}><Play className="h-4 w-4 mr-2" /> Resume</Button>
        ) : (
          <Button variant="outline" onClick={() => quickAction("pause")} disabled={captureStatus !== "running"}><Pause className="h-4 w-4 mr-2" /> Pause</Button>
        )}
        <Button variant="outline" onClick={() => quickAction("stop")}><Square className="h-4 w-4 mr-2" /> Stop</Button>
        <Button variant="outline" onClick={() => quickAction("test")}><Camera className="h-4 w-4 mr-2" /> Test shot</Button>
        <Button variant="outline" onClick={() => quickAction("single")}><Camera className="h-4 w-4 mr-2" /> Queue single</Button>
        <Button variant="outline" onClick={load}><RefreshCw className="h-4 w-4 mr-2" /> Refresh</Button>
        <Button variant="outline" onClick={() => quickAction("timelapse")}><Film className="h-4 w-4 mr-2" /> Queue timelapse</Button>
        <Button variant="ghost" onClick={() => toast.message("Use systemctl restart skyweaver.target on the Pi")}><RotateCw className="h-4 w-4 mr-2" /> Restart services</Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2 telemetry-card p-0 overflow-hidden">
          <div className="aspect-video relative bg-black">
            <img src={latest?.public_url ?? sampleSky} alt="Latest all-sky capture" className="absolute inset-0 w-full h-full object-cover" />
            <div className="absolute inset-0 bg-gradient-to-t from-background via-transparent to-transparent" />
            <div className="absolute bottom-0 left-0 right-0 p-4 flex items-end justify-between">
              <div>
                <p className="text-xs uppercase tracking-widest text-muted-foreground">Latest capture</p>
                <p className="text-sm font-mono-data">{latest ? format(new Date(latest.captured_at), "yyyy-MM-dd HH:mm:ss") : "No images yet"}</p>
              </div>
              <div className="flex gap-2">
                <StatusBadge variant="ok">{latest?.exposure_ms ? `${(latest.exposure_ms / 1000).toFixed(2)}s` : "no exposure"}</StatusBadge>
                <StatusBadge variant="active">gain {latest?.gain ?? "-"}</StatusBadge>
              </div>
            </div>
          </div>
        </Card>

        <Card className="telemetry-card space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Camera</h3>
            <Camera className="h-4 w-4 text-primary" />
          </div>
          <div>
            <p className="text-lg font-semibold">{camera?.name ?? "No camera configured"}</p>
            <p className="text-xs text-muted-foreground font-mono-data">{camera?.model ?? camera?.adapter ?? "-"}</p>
          </div>
          <dl className="grid grid-cols-2 gap-3 text-xs font-mono-data">
            <Stat k="Mode" v={status?.capture?.current_mode ?? "-"} />
            <Stat k="Adapter" v={camera?.adapter ?? "-"} />
            <Stat k="Temp" v={latest?.temperature_c ? `${latest.temperature_c.toFixed(1)} C` : "-"} />
            <Stat k="Format" v={latest?.format?.toUpperCase() ?? "-"} />
            <Stat k="Stars" v={latest?.star_count ?? "-"} />
            <Stat k="Cloud" v={latest?.cloud_score ?? "-"} />
            <Stat k="Last job" v={formatDaemonJob(status?.capture)} />
            <Stat k="Last ok" v={formatRelative(status?.capture?.daemon_last_success_at)} />
          </dl>
        </Card>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <MetricCard icon={<Cpu className="h-4 w-4" />} label="CPU" value={`${metrics.cpu_percent.toFixed(0)}%`} pct={metrics.cpu_percent} />
        <MetricCard icon={<MemoryStick className="h-4 w-4" />} label="Memory" value={`${metrics.memory_percent.toFixed(0)}%`} pct={metrics.memory_percent} />
        <MetricCard icon={<HardDrive className="h-4 w-4" />} label="Disk" value={`${metrics.disk_percent.toFixed(0)}%`} pct={metrics.disk_percent} />
        <MetricCard icon={<Thermometer className="h-4 w-4" />} label="Temp" value={metrics.temperature_c ? `${metrics.temperature_c.toFixed(0)}C` : "-"} pct={metrics.temperature_c ? (metrics.temperature_c / 85) * 100 : 0} accent />
        <MetricCard icon={<Activity className="h-4 w-4" />} label="Uptime" value={`${Math.floor(metrics.uptime_seconds / 3600)}h`} pct={100} />
      </div>

      <Card className="telemetry-card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2"><Clock className="h-4 w-4 text-primary" /> Tonight</h3>
          <div className="flex items-center gap-2">
            <StatusBadge variant={schedulePreview?.active ? "active" : schedulePreview?.enabled ? "idle" : "warn"} pulse={schedulePreview?.active}>{schedulePreview?.active ? "window active" : schedulePreview?.enabled ? "waiting" : "disabled"}</StatusBadge>
            <span className="text-xs text-muted-foreground font-mono-data">{schedulePreview?.timezone ?? observatory.timezone}</span>
          </div>
        </div>
        <div className="grid grid-cols-4 lg:grid-cols-8 gap-2 text-xs font-mono-data">
          {Object.entries(timeline).map(([key, value]) => <div key={key}><p className="text-muted-foreground">{key}</p><p>{formatTimelineValue(value)}</p></div>)}
        </div>
        <div className="mt-4 pt-4 border-t border-border flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 text-xs font-mono-data">
          <span className="text-muted-foreground">Capture window: {formatScheduleTime(schedulePreview?.window_start)} to {formatScheduleTime(schedulePreview?.window_end)}</span>
          <span>Next: {schedulePreview?.next_transition_at ? `${schedulePreview.next_state} ${formatDistanceToNow(new Date(schedulePreview.next_transition_at), { addSuffix: true })}` : "-"}</span>
        </div>
      </Card>

      <Card className="telemetry-card space-y-4">
        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-widest text-muted-foreground">Capture queue</p>
            <h3 className="text-lg font-semibold">Sequence capture</h3>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 lg:min-w-[680px]">
            <NumberField label="Frames" value={sequenceForm.count} min={1} max={100} onChange={(count) => setSequenceForm({ ...sequenceForm, count })} />
            <NumberField label="Delay s" value={sequenceForm.delay_seconds} min={0} max={3600} onChange={(delay_seconds) => setSequenceForm({ ...sequenceForm, delay_seconds })} />
            <NumberField label="Exposure ms" value={sequenceForm.exposure_ms} min={1} onChange={(exposure_ms) => setSequenceForm({ ...sequenceForm, exposure_ms })} />
            <NumberField label="Gain" value={sequenceForm.gain} min={0} step={0.1} onChange={(gain) => setSequenceForm({ ...sequenceForm, gain })} />
            <Button onClick={queueSequence} className="bg-gradient-primary text-primary-foreground md:self-end"><Play className="h-4 w-4 mr-2" /> Queue</Button>
          </div>
        </div>
        <div className="space-y-3">
          {captureJobs.map((job) => (
            <div key={job.id} className="rounded-md border border-border bg-muted/20 p-3">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="font-medium capitalize">{job.type.replaceAll("_", " ")}</p>
                    <StatusBadge variant={jobStatusVariant(job.status)}>{job.status}</StatusBadge>
                  </div>
                  <p className="text-xs text-muted-foreground font-mono-data truncate">{formatJobDetail(job)}</p>
                </div>
                <span className="text-xs font-mono-data text-muted-foreground">{Math.round((job.progress ?? 0) * 100)}%</span>
              </div>
              {job.error && <p className="text-xs text-status-error mt-2">{job.error}</p>}
              <Progress value={Math.round((job.progress ?? 0) * 100)} className="h-1 mt-3" />
            </div>
          ))}
          {captureJobs.length === 0 && <p className="text-sm text-muted-foreground">No capture jobs queued yet.</p>}
        </div>
      </Card>

      <Card className="telemetry-card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Recent captures</h3>
          <span className="text-xs text-muted-foreground font-mono-data">{images.length} shown</span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
          {images.map((img) => (
            <div key={img.id} className="group relative aspect-square rounded-md overflow-hidden border border-border bg-muted/40">
              <img src={img.public_url ?? sampleSky} loading="lazy" alt="" className="w-full h-full object-cover opacity-90 group-hover:opacity-100 group-hover:scale-105 transition" />
              <div className="absolute bottom-0 left-0 right-0 p-1.5 bg-gradient-to-t from-background/95 to-transparent">
                <p className="text-[10px] font-mono-data text-foreground">{format(new Date(img.captured_at), "HH:mm")}</p>
                <p className="text-[9px] text-muted-foreground">{formatDistanceToNow(new Date(img.captured_at), { addSuffix: true })}</p>
              </div>
            </div>
          ))}
          {images.length === 0 && <p className="col-span-full text-sm text-muted-foreground">No captures yet. Try a mock test shot.</p>}
        </div>
      </Card>
    </div>
  );
}

function Stat({ k, v }: { k: string; v: React.ReactNode }) {
  return <div className="flex flex-col gap-0.5 p-2 rounded-md bg-muted/40"><dt className="text-[10px] uppercase tracking-widest text-muted-foreground">{k}</dt><dd>{v}</dd></div>;
}

function MetricCard({ icon, label, value, pct, accent = false }: { icon: React.ReactNode; label: string; value: string; pct: number; accent?: boolean }) {
  return (
    <Card className="telemetry-card">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] uppercase tracking-widest text-muted-foreground flex items-center gap-1.5">{icon}{label}</span>
      </div>
      <div className={`text-2xl font-semibold font-mono-data ${accent ? "text-accent" : ""}`}>{value}</div>
      <Progress value={Math.max(0, Math.min(100, pct))} className="mt-3 h-1" />
    </Card>
  );
}

function NumberField({ label, value, onChange, ...rest }: { label: string; value: number; onChange: (value: number) => void } & Omit<React.InputHTMLAttributes<HTMLInputElement>, "onChange" | "type" | "value">) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <Input type="number" value={String(value)} onChange={(event) => onChange(Number(event.target.value || 0))} {...rest} />
    </div>
  );
}

function formatScheduleTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  return isValidDate(date) ? format(date, "HH:mm") : "-";
}

function formatRelative(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  return isValidDate(date) ? formatDistanceToNow(date, { addSuffix: true }) : "-";
}

function formatDaemonJob(capture: any) {
  if (!capture?.daemon_last_claimed_job_type) return "-";
  const when = formatRelative(capture.daemon_last_claimed_at);
  return `${capture.daemon_last_claimed_job_type} ${when}`;
}

function formatJobDetail(job: CaptureJob) {
  const request = job.request ?? {};
  const capture = request.capture ?? request;
  const result = job.result;
  const count = request.count ?? request.frames;
  const completed = result?.completed_count;
  if (job.type === "sequence") return `${completed ?? 0}/${count ?? "-"} frames - job ${job.id}`;
  if (result?.image_id) return `image ${result.image_id} - job ${job.id}`;
  return `${capture?.exposure_ms ?? "-"} ms, gain ${capture?.gain ?? "-"} - job ${job.id}`;
}

function jobStatusVariant(status?: string): "ok" | "warn" | "error" | "idle" | "active" {
  if (status === "completed") return "ok";
  if (status === "failed" || status === "canceled") return "error";
  if (status === "running" || status === "claimed") return "active";
  if (status === "pending") return "warn";
  return "idle";
}

function formatCoordinate(value: number) {
  return Number.isFinite(value) ? value.toFixed(4) : "-";
}

function formatTimelineValue(value?: Date | null) {
  return isValidDate(value) ? format(value, "HH:mm") : "-";
}

function isValidDate(value?: Date | null): value is Date {
  return value instanceof Date && Number.isFinite(value.getTime());
}
