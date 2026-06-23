import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { StatusBadge } from "@/components/StatusBadge";
import { SkyApi, type ProcessingJob, type ProductRow } from "@/lib/api";
import { Download, Film, Plus, RefreshCw } from "lucide-react";
import { toast } from "sonner";

export default function Timelapses() {
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [products, setProducts] = useState<ProductRow[]>([]);
  const [form, setForm] = useState({ day_key: new Date().toISOString().slice(0, 10).replaceAll("-", ""), fps: 30, codec: "h264" });

  useEffect(() => {
    document.title = "Night products - Sky Weaver Hub";
    load();
    const timer = window.setInterval(load, 5000);
    return () => window.clearInterval(timer);
  }, []);

  async function load() {
    try {
      const [nextJobs, nextProducts] = await Promise.all([SkyApi.processingJobs(), SkyApi.products()]);
      setJobs(nextJobs.filter((job) => ["thumbnail", "keogram", "timelapse", "mini_timelapse", "startrail"].includes(job.type)));
      setProducts(nextProducts);
    } catch {
      setJobs([]);
      setProducts([]);
    }
  }

  async function create(type: string) {
    try {
      const job = await SkyApi.createProduct(type, { day_key: form.day_key, fps: form.fps, codec: form.codec });
      toast.success(`${type} queued`);
      setJobs([{ ...job, type: type.replace("-", "_"), input: { day_key: form.day_key, fps: form.fps, codec: form.codec }, progress: job.progress ?? 0 }, ...jobs]);
    } catch (e: any) {
      toast.error(e.message ?? "Queue failed");
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-widest text-muted-foreground">Processing</p>
        <h1 className="text-3xl font-semibold tracking-tight flex items-center gap-3"><Film className="h-7 w-7 text-primary" /> Night products</h1>
      </div>

      <Card className="telemetry-card grid grid-cols-1 md:grid-cols-5 gap-4 items-end">
        <Labelled label="Day key"><Input value={form.day_key} onChange={(e) => setForm({ ...form, day_key: e.target.value })} placeholder="20260623" /></Labelled>
        <Labelled label="FPS"><Input type="number" value={form.fps} onChange={(e) => setForm({ ...form, fps: parseInt(e.target.value || "30") })} /></Labelled>
        <Labelled label="Codec"><Input value={form.codec} onChange={(e) => setForm({ ...form, codec: e.target.value })} /></Labelled>
        <Button onClick={() => create("timelapse")} className="bg-gradient-primary text-primary-foreground"><Plus className="h-4 w-4 mr-2" /> Timelapse</Button>
        <Button variant="outline" onClick={() => create("keogram")}>Keogram</Button>
        <Button variant="outline" onClick={() => create("startrail")} className="md:col-start-4">Startrail</Button>
        <Button variant="outline" onClick={() => create("mini-timelapse")}>Mini timelapse</Button>
      </Card>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Processing queue</h2>
          <Button variant="ghost" size="sm" onClick={load}><RefreshCw className="h-4 w-4 mr-2" /> Refresh</Button>
        </div>
        {jobs.map((j) => (
          <Card key={j.id} className="telemetry-card flex items-center gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3">
                <p className="font-medium truncate">{prettyType(j.type)}</p>
                <StatusBadge variant={statusVariant(j.status)}>{j.status ?? "queued"}</StatusBadge>
              </div>
              <p className="text-xs text-muted-foreground font-mono-data mt-1">day {j.input?.day_key ?? j.output?.day_key ?? "-"} - job {j.id}</p>
              {j.error && <p className="text-xs text-status-error mt-2">{j.error}</p>}
              <Progress value={Math.round((j.progress ?? 0) * 100)} className="h-1 mt-3" />
            </div>
          </Card>
        ))}
        {jobs.length === 0 && <p className="text-sm text-muted-foreground">No processing jobs yet. Queue one from a mock capture day.</p>}
      </div>

      <div className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Generated products</h2>
        {products.map((product) => (
          <Card key={product.id} className="telemetry-card flex items-center gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3">
                <p className="font-medium truncate">{prettyType(product.type)}</p>
                <StatusBadge variant={statusVariant(product.status)}>{product.status}</StatusBadge>
              </div>
              <p className="text-xs text-muted-foreground font-mono-data mt-1">day {product.day_key} - {product.metadata?.source_images ?? "-"} source images</p>
            </div>
            <Button asChild variant="outline" size="sm">
              <a href={`/api/v1/products/${product.id}/download`} target="_blank" rel="noreferrer"><Download className="h-4 w-4 mr-2" /> Download</a>
            </Button>
          </Card>
        ))}
        {products.length === 0 && <p className="text-sm text-muted-foreground">No generated products yet.</p>}
      </div>
    </div>
  );
}

function Labelled({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="space-y-2"><Label>{label}</Label>{children}</div>;
}

function prettyType(type: string) {
  return type.replaceAll("_", " ").replaceAll("-", " ");
}

function statusVariant(status?: string): "ok" | "warn" | "error" | "idle" | "active" {
  if (status === "completed") return "ok";
  if (status === "failed") return "error";
  if (status === "running") return "active";
  if (status === "pending") return "warn";
  return "idle";
}
