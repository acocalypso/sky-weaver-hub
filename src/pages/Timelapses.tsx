import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { StatusBadge } from "@/components/StatusBadge";
import { SkyApi } from "@/lib/api";
import { Film, Plus } from "lucide-react";
import { toast } from "sonner";

interface ProductJob {
  id: string;
  type: string;
  day_key?: string;
  status?: string;
  progress?: number;
  created_at?: string;
}

export default function Timelapses() {
  const [jobs, setJobs] = useState<ProductJob[]>([]);
  const [form, setForm] = useState({ day_key: new Date().toISOString().slice(0, 10).replaceAll("-", ""), fps: 30, codec: "h264" });

  useEffect(() => { document.title = "Night products - Sky Weaver Hub"; load(); }, []);

  async function load() {
    try { setJobs(await SkyApi.products()); } catch { setJobs([]); }
  }

  async function create(type: string) {
    try {
      const job = await SkyApi.createProduct(type, { day_key: form.day_key, fps: form.fps, codec: form.codec });
      toast.success(`${type} queued`);
      setJobs([{ id: job.id, type, day_key: form.day_key, status: job.status, progress: 0 }, ...jobs]);
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
        {jobs.map((j) => (
          <Card key={j.id} className="telemetry-card flex items-center gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3">
                <p className="font-medium truncate">{j.type}</p>
                <StatusBadge variant={j.status === "completed" ? "ok" : j.status === "failed" ? "error" : "warn"}>{j.status ?? "queued"}</StatusBadge>
              </div>
              <p className="text-xs text-muted-foreground font-mono-data mt-1">day {j.day_key ?? "-"} - job {j.id}</p>
              <Progress value={j.progress ?? 0} className="h-1 mt-3" />
            </div>
          </Card>
        ))}
        {jobs.length === 0 && <p className="text-sm text-muted-foreground">No generated products yet. Queue one from a mock capture day.</p>}
      </div>
    </div>
  );
}

function Labelled({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="space-y-2"><Label>{label}</Label>{children}</div>;
}
