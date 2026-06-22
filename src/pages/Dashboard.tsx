import { useEffect, useMemo, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { StatusBadge } from "@/components/StatusBadge";
import { supabase } from "@/integrations/supabase/client";
import { getTonightTimeline, getSunAltitude } from "@/lib/sun";
import sampleSky from "@/assets/sample-sky-1.jpg";
import {
  Play, Square, Camera, RefreshCw, Film, RotateCw,
  Cpu, MemoryStick, HardDrive, Thermometer, Activity, Clock,
} from "lucide-react";
import { toast } from "sonner";
import { formatDistanceToNow, format } from "date-fns";

interface ImageRow {
  id: string;
  captured_at: string;
  storage_path: string;
  metadata: any;
  star_count: number | null;
  cloud_score: number | null;
}
interface CameraRow { id: string; name: string; model: string | null; status: string; }
interface SettingsRow {
  observatory_name: string; latitude: number; longitude: number; timezone: string;
}
interface CaptureSettingsRow {
  exposure_us: number; gain: number; resolution: string; file_format: string; white_balance: string; binning: number;
}

export default function Dashboard() {
  const [images, setImages] = useState<ImageRow[]>([]);
  const [camera, setCamera] = useState<CameraRow | null>(null);
  const [settings, setSettings] = useState<SettingsRow | null>(null);
  const [capSettings, setCapSettings] = useState<CaptureSettingsRow | null>(null);
  const [captureState, setCaptureState] = useState<"idle" | "capturing" | "scheduled" | "error">("scheduled");
  const [metrics, setMetrics] = useState({ cpu: 22, mem: 41, disk: 58, temp: 47, uptimeH: 36 });

  useEffect(() => { document.title = "Dashboard · AllSky Control Hub"; }, []);

  useEffect(() => {
    const load = async () => {
      const [imgRes, camRes, setRes] = await Promise.all([
        supabase.from("images").select("id, captured_at, storage_path, metadata, star_count, cloud_score").order("captured_at", { ascending: false }).limit(8),
        supabase.from("cameras").select("id, name, model, status").eq("is_default", true).maybeSingle(),
        supabase.from("system_settings").select("observatory_name, latitude, longitude, timezone").eq("id", 1).maybeSingle(),
      ]);
      if (imgRes.data) setImages(imgRes.data as ImageRow[]);
      if (camRes.data) {
        setCamera(camRes.data as CameraRow);
        const { data: cs } = await supabase.from("camera_settings")
          .select("exposure_us, gain, resolution, file_format, white_balance, binning")
          .eq("camera_id", (camRes.data as any).id).maybeSingle();
        if (cs) setCapSettings(cs as CaptureSettingsRow);
      }
      if (setRes.data) setSettings(setRes.data as SettingsRow);
    };
    load();

    // Mocked live system metrics
    const t = setInterval(() => {
      setMetrics((m) => ({
        cpu: Math.max(8, Math.min(95, m.cpu + (Math.random() - 0.5) * 8)),
        mem: Math.max(15, Math.min(92, m.mem + (Math.random() - 0.5) * 4)),
        disk: m.disk,
        temp: Math.max(35, Math.min(72, m.temp + (Math.random() - 0.5) * 1.5)),
        uptimeH: m.uptimeH,
      }));
    }, 2000);

    // Realtime new images
    const ch = supabase.channel("dashboard-events")
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "images" }, (p) => {
        setImages((cur) => [p.new as ImageRow, ...cur].slice(0, 8));
        toast.success("New image captured");
      })
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "realtime_events" }, (p) => {
        const ev = (p.new as any).type;
        if (ev === "capture_started") setCaptureState("capturing");
        if (ev === "capture_stopped") setCaptureState("idle");
      })
      .subscribe();

    return () => { clearInterval(t); supabase.removeChannel(ch); };
  }, []);

  const timeline = useMemo(() => {
    if (!settings) return null;
    return getTonightTimeline(Number(settings.latitude), Number(settings.longitude));
  }, [settings]);

  const sunAlt = useMemo(() => {
    if (!settings) return 0;
    return getSunAltitude(Number(settings.latitude), Number(settings.longitude));
  }, [settings]);

  const exposureSec = capSettings ? (capSettings.exposure_us / 1_000_000).toFixed(2) : "—";

  const quickAction = async (type: string) => {
    await supabase.from("realtime_events").insert({ type, payload: { source: "dashboard" } });
    if (type === "capture_started") { setCaptureState("capturing"); toast.success("Capture started"); }
    else if (type === "capture_stopped") { setCaptureState("idle"); toast.success("Capture stopped"); }
    else if (type === "test_shot") {
      toast.success("Test shot queued (mock adapter)");
      // simulate inserting an image
      await supabase.from("images").insert({
        camera_id: camera?.id,
        storage_path: "demo/sample-sky-1.jpg",
        thumb_path: "demo/sample-sky-1.jpg",
        metadata: { exposure_us: capSettings?.exposure_us ?? 5_000_000, gain: capSettings?.gain ?? 250, source: "test_shot" },
        tags: ["test"],
      });
    } else {
      toast.success(`Event: ${type}`);
    }
  };

  const latest = images[0];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground">Observatory</p>
          <h1 className="text-3xl font-semibold tracking-tight">{settings?.observatory_name ?? "—"}</h1>
          <p className="text-sm text-muted-foreground mt-1 font-mono-data">
            {settings ? `${Number(settings.latitude).toFixed(4)}° , ${Number(settings.longitude).toFixed(4)}°` : "—"}
            {"  ·  "}Sun alt {sunAlt.toFixed(1)}°
          </p>
        </div>
        <div className="flex items-center gap-3">
          <StatusBadge
            variant={captureState === "capturing" ? "active" : captureState === "error" ? "error" : captureState === "scheduled" ? "warn" : "idle"}
            pulse={captureState === "capturing"}
          >
            {captureState}
          </StatusBadge>
          <StatusBadge variant={camera?.status === "connected" ? "ok" : "error"}>
            {camera?.status ?? "no camera"}
          </StatusBadge>
        </div>
      </div>

      {/* Quick actions */}
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => quickAction("capture_started")} className="bg-gradient-primary text-primary-foreground hover:opacity-90">
          <Play className="h-4 w-4 mr-2" /> Start capture
        </Button>
        <Button variant="outline" onClick={() => quickAction("capture_stopped")}><Square className="h-4 w-4 mr-2" /> Stop</Button>
        <Button variant="outline" onClick={() => quickAction("test_shot")}><Camera className="h-4 w-4 mr-2" /> Test shot</Button>
        <Button variant="outline" onClick={() => quickAction("camera_refresh")}><RefreshCw className="h-4 w-4 mr-2" /> Refresh camera</Button>
        <Button variant="outline" onClick={() => quickAction("timelapse_requested")}><Film className="h-4 w-4 mr-2" /> Generate timelapse</Button>
        <Button variant="ghost" onClick={() => quickAction("services_restart")}><RotateCw className="h-4 w-4 mr-2" /> Restart services</Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Latest image */}
        <Card className="lg:col-span-2 telemetry-card p-0 overflow-hidden">
          <div className="aspect-video relative bg-black">
            <img
              src={sampleSky}
              alt="Latest all-sky capture"
              width={1024}
              height={1024}
              className="absolute inset-0 w-full h-full object-cover"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-background via-transparent to-transparent" />
            <div className="absolute bottom-0 left-0 right-0 p-4 flex items-end justify-between">
              <div>
                <p className="text-xs uppercase tracking-widest text-muted-foreground">Latest capture</p>
                <p className="text-sm font-mono-data">
                  {latest ? format(new Date(latest.captured_at), "yyyy-MM-dd HH:mm:ss") : "—"}
                </p>
              </div>
              <div className="flex gap-2">
                <StatusBadge variant="ok">{exposureSec}s</StatusBadge>
                <StatusBadge variant="active">gain {capSettings?.gain ?? "—"}</StatusBadge>
              </div>
            </div>
          </div>
        </Card>

        {/* Camera card */}
        <Card className="telemetry-card space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Camera</h3>
            <Camera className="h-4 w-4 text-primary" />
          </div>
          <div>
            <p className="text-lg font-semibold">{camera?.name ?? "—"}</p>
            <p className="text-xs text-muted-foreground font-mono-data">{camera?.model ?? "—"}</p>
          </div>
          <dl className="grid grid-cols-2 gap-3 text-xs font-mono-data">
            {[
              ["Exposure", `${exposureSec} s`],
              ["Gain", capSettings?.gain ?? "—"],
              ["Resolution", capSettings?.resolution ?? "—"],
              ["Format", (capSettings?.file_format ?? "—").toUpperCase()],
              ["WB", capSettings?.white_balance ?? "—"],
              ["Binning", capSettings?.binning ?? "—"],
            ].map(([k, v]) => (
              <div key={k as string} className="flex flex-col gap-0.5 p-2 rounded-md bg-muted/40">
                <dt className="text-[10px] uppercase tracking-widest text-muted-foreground">{k}</dt>
                <dd className="text-foreground">{v as React.ReactNode}</dd>
              </div>
            ))}
          </dl>
        </Card>
      </div>

      {/* System health */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <MetricCard icon={<Cpu className="h-4 w-4" />} label="CPU" value={`${metrics.cpu.toFixed(0)}%`} pct={metrics.cpu} />
        <MetricCard icon={<MemoryStick className="h-4 w-4" />} label="Memory" value={`${metrics.mem.toFixed(0)}%`} pct={metrics.mem} />
        <MetricCard icon={<HardDrive className="h-4 w-4" />} label="Disk" value={`${metrics.disk.toFixed(0)}%`} pct={metrics.disk} />
        <MetricCard icon={<Thermometer className="h-4 w-4" />} label="Temp" value={`${metrics.temp.toFixed(0)}°C`} pct={(metrics.temp / 85) * 100} accent />
        <MetricCard icon={<Activity className="h-4 w-4" />} label="Uptime" value={`${metrics.uptimeH}h`} pct={100} />
      </div>

      {/* Tonight timeline */}
      <Card className="telemetry-card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
            <Clock className="h-4 w-4 text-primary" /> Tonight
          </h3>
          <span className="text-xs text-muted-foreground font-mono-data">{settings?.timezone}</span>
        </div>
        {timeline ? (
          <Timeline timeline={timeline} />
        ) : (
          <p className="text-sm text-muted-foreground">Configure location in Settings to see twilight times.</p>
        )}
      </Card>

      {/* Recent gallery */}
      <Card className="telemetry-card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Recent captures</h3>
          <span className="text-xs text-muted-foreground font-mono-data">{images.length} shown</span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
          {images.map((img) => (
            <div key={img.id} className="group relative aspect-square rounded-md overflow-hidden border border-border bg-muted/40">
              <img src={sampleSky} loading="lazy" width={256} height={256} alt="" className="w-full h-full object-cover opacity-90 group-hover:opacity-100 group-hover:scale-105 transition" />
              <div className="absolute bottom-0 left-0 right-0 p-1.5 bg-gradient-to-t from-background/95 to-transparent">
                <p className="text-[10px] font-mono-data text-foreground">{format(new Date(img.captured_at), "HH:mm")}</p>
                <p className="text-[9px] text-muted-foreground">{formatDistanceToNow(new Date(img.captured_at), { addSuffix: true })}</p>
              </div>
            </div>
          ))}
          {images.length === 0 && (
            <p className="col-span-full text-sm text-muted-foreground">No captures yet.</p>
          )}
        </div>
      </Card>
    </div>
  );
}

function MetricCard({ icon, label, value, pct, accent = false }: {
  icon: React.ReactNode; label: string; value: string; pct: number; accent?: boolean;
}) {
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

function Timeline({ timeline }: { timeline: ReturnType<typeof getTonightTimeline> }) {
  const points = [
    { key: "sunset", label: "Sunset", t: timeline.sunset, color: "hsl(35 95% 60%)" },
    { key: "civilDusk", label: "Civil dusk", t: timeline.civilDusk, color: "hsl(20 80% 55%)" },
    { key: "nauticalDusk", label: "Nautical", t: timeline.nauticalDusk, color: "hsl(245 60% 60%)" },
    { key: "astronomicalDusk", label: "Astro dusk", t: timeline.astronomicalDusk, color: "hsl(188 92% 56%)" },
    { key: "astronomicalDawn", label: "Astro dawn", t: timeline.astronomicalDawn, color: "hsl(188 92% 56%)" },
    { key: "nauticalDawn", label: "Nautical", t: timeline.nauticalDawn, color: "hsl(245 60% 60%)" },
    { key: "civilDawn", label: "Civil dawn", t: timeline.civilDawn, color: "hsl(20 80% 55%)" },
    { key: "sunrise", label: "Sunrise", t: timeline.sunrise, color: "hsl(35 95% 60%)" },
  ];
  const now = new Date();
  const start = timeline.sunset.getTime();
  const end = timeline.sunrise.getTime() < start
    ? timeline.sunrise.getTime() + 24 * 3600 * 1000
    : timeline.sunrise.getTime();
  const span = end - start;
  const nowPct = Math.max(0, Math.min(100, ((now.getTime() - start) / span) * 100));

  return (
    <div className="space-y-4">
      <div className="relative h-2 rounded-full bg-gradient-to-r from-[hsl(35_95%_60%)] via-[hsl(245_70%_25%)] to-[hsl(35_95%_60%)] overflow-visible">
        <div className="absolute -top-1 h-4 w-0.5 bg-primary glow-primary" style={{ left: `${nowPct}%` }} />
      </div>
      <div className="grid grid-cols-4 lg:grid-cols-8 gap-2">
        {points.map((p) => {
          const pt = p.t.getTime() < start ? p.t.getTime() + 24 * 3600 * 1000 : p.t.getTime();
          const past = now.getTime() > pt;
          return (
            <div key={p.key} className="space-y-1">
              <div className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: p.color, boxShadow: `0 0 6px ${p.color}` }} />
                <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{p.label}</span>
              </div>
              <div className={`text-xs font-mono-data ${past ? "text-muted-foreground" : "text-foreground"}`}>
                {isNaN(p.t.getTime()) ? "—" : format(p.t, "HH:mm")}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
