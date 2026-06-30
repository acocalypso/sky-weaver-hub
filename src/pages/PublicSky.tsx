import { useEffect, useState } from "react";
import { format, formatDistanceToNow } from "date-fns";
import { Camera, Clock, ImageOff, RefreshCw, Telescope } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/StatusBadge";
import { SkyApi, type PublicLatestImage } from "@/lib/api";
import sampleSky from "@/assets/sample-sky-1.jpg";

export default function PublicSky() {
  const [latest, setLatest] = useState<PublicLatestImage | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "empty" | "disabled" | "error">("loading");
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  useEffect(() => {
    document.title = "Public sky - Sky Weaver Hub";
    load();
    const timer = window.setInterval(load, 30000);
    return () => window.clearInterval(timer);
  }, []);

  async function load() {
    try {
      const data = await SkyApi.publicLatest();
      setLatest(data);
      setStatus("ready");
      setUpdatedAt(new Date());
    } catch (error) {
      setLatest(null);
      const message = error instanceof Error ? error.message : "";
      if (message.toLowerCase().includes("public page is disabled")) {
        setStatus("disabled");
      } else {
        setStatus((current) => (current === "ready" ? "error" : "empty"));
      }
      setUpdatedAt(new Date());
    }
  }

  const imageUrl = latest ? `${latest.download_url}?v=${encodeURIComponent(latest.id)}` : sampleSky;

  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="starfield" />
      <section className="relative z-10 min-h-screen grid grid-rows-[auto_1fr_auto]">
        <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between px-4 py-4 sm:px-6 lg:px-8 border-b border-border/60 bg-background/70 backdrop-blur-md">
          <div className="flex items-center gap-3 min-w-0">
            <div className="h-10 w-10 rounded-md border border-primary/30 bg-primary/10 grid place-items-center shrink-0">
              <Telescope className="h-5 w-5 text-primary" />
            </div>
            <div className="min-w-0">
              <h1 className="text-xl font-semibold leading-tight truncate">Sky Weaver Public Sky</h1>
              <p className="text-xs text-muted-foreground font-mono-data truncate">{latest ? formatCaptureTime(latest.captured_at) : emptySubtitle(status)}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge variant={status === "ready" ? "ok" : status === "error" ? "warn" : status === "disabled" ? "error" : "idle"} pulse={status === "ready"}>{statusLabel(status)}</StatusBadge>
            <Button variant="outline" size="sm" onClick={load} aria-label="Refresh public sky">
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </header>

        <div className="relative overflow-hidden bg-black">
          <img src={imageUrl} alt="Latest public all-sky capture" className="absolute inset-0 h-full w-full object-contain" />
          {!latest && (
            <div className="absolute inset-0 grid place-items-center bg-background/70">
              <div className="flex flex-col items-center gap-3 text-center px-4">
                <ImageOff className="h-10 w-10 text-muted-foreground" />
                <p className="text-lg font-medium">{emptyTitle(status)}</p>
              </div>
            </div>
          )}
          <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-background/95 via-background/45 to-transparent p-2.5 sm:p-4 lg:p-6">
            <div data-testid="public-stats" className="grid grid-flow-col auto-cols-[minmax(8.5rem,1fr)] gap-2 overflow-x-auto pb-1 sm:grid-flow-row sm:grid-cols-3 sm:overflow-visible lg:grid-cols-5">
              <PublicStat icon={<Clock className="h-4 w-4" />} label="Captured" value={latest ? formatRelative(latest.captured_at) : "-"} />
              <PublicStat icon={<Camera className="h-4 w-4" />} label="Mode" value={latest?.mode ?? "-"} />
              <PublicStat label="Format" value={latest?.format?.toUpperCase() ?? "-"} />
              <PublicStat label="Frame" value={formatDimensions(latest)} />
              <PublicStat label="Size" value={formatBytes(latest?.size_bytes)} />
            </div>
          </div>
        </div>

        <footer className="relative z-10 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between px-4 py-3 sm:px-6 lg:px-8 border-t border-border/60 bg-background/80 backdrop-blur-md text-xs text-muted-foreground font-mono-data">
          <span>{updatedAt ? `Checked ${formatDistanceToNow(updatedAt, { addSuffix: true })}` : "Checking latest image"}</span>
          <span>{latest?.day_key ?? "No day key"}</span>
        </footer>
      </section>
    </main>
  );
}

function PublicStat({ label, value, icon }: { label: string; value: string; icon?: React.ReactNode }) {
  return (
    <div className="min-w-0 rounded-md border border-border/50 bg-background/65 px-2.5 py-1.5 backdrop-blur-sm sm:px-3 sm:py-2">
      <p className="text-[9px] uppercase tracking-wider text-muted-foreground flex items-center gap-1 min-w-0 sm:text-[10px]">{icon}{label}</p>
      <p className="mt-0.5 font-mono-data text-xs text-foreground truncate sm:mt-1 sm:text-sm">{value}</p>
    </div>
  );
}

function statusLabel(status: "loading" | "ready" | "empty" | "disabled" | "error") {
  if (status === "ready") return "live";
  if (status === "error") return "stale";
  if (status === "disabled") return "disabled";
  if (status === "loading") return "loading";
  return "waiting";
}

function emptyTitle(status: "loading" | "ready" | "empty" | "disabled" | "error") {
  if (status === "disabled") return "Public page disabled";
  if (status === "error") return "Public sky unavailable";
  return "No public capture yet";
}

function emptySubtitle(status: "loading" | "ready" | "empty" | "disabled" | "error") {
  if (status === "disabled") return "Disabled in Sky Weaver settings";
  if (status === "error") return "Keeping the public page ready";
  return "Waiting for first capture";
}

function formatCaptureTime(value: string) {
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? format(date, "yyyy-MM-dd HH:mm:ss") : value;
}

function formatRelative(value: string) {
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? formatDistanceToNow(date, { addSuffix: true }) : "-";
}

function formatDimensions(image: PublicLatestImage | null) {
  if (!image?.width || !image.height) return "-";
  return `${image.width} x ${image.height}`;
}

function formatBytes(value?: number | null) {
  if (!value) return "-";
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}
