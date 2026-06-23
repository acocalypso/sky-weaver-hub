import { useEffect, useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { StatusBadge } from "@/components/StatusBadge";
import { Film, Plus } from "lucide-react";
import { toast } from "sonner";
import { format } from "date-fns";

interface Job {
  id: string; name: string; date_from: string; date_to: string;
  fps: number; codec: string; state: string; progress: number; output_path: string | null;
  created_at: string;
}

export default function Timelapses() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [form, setForm] = useState({ name: "", date_from: "", date_to: "", fps: 30, codec: "h264" });

  useEffect(() => {
    document.title = "Timelapses · AllSky Control Hub";
    load();
    const t = setInterval(simulate, 2500);
    return () => clearInterval(t);
  }, []);

  async function load() {
    const { data } = await supabase.from("timelapse_jobs").select("*").order("created_at", { ascending: false }).limit(50);
    setJobs((data ?? []) as Job[]);
  }

  async function simulate() {
    const { data: queue } = await supabase.from("timelapse_jobs").select("*").in("state", ["pending", "running"]).order("created_at");
    if (!queue || queue.length === 0) return;
    const job = queue[0] as Job;
    let next: any = {};
    if (job.state === "pending") next = { state: "running", progress: 5 };
    else {
      const p = Math.min(100, job.progress + 15 + Math.random() * 10);
      next = p >= 100
        ? { state: "complete", progress: 100, output_path: `/var/lib/allsky/timelapses/${job.id}.mp4` }
        : { progress: Math.round(p) };
    }
    await supabase.from("timelapse_jobs").update(next).eq("id", job.id);
    load();
  }

  async function create() {
    if (!form.name || !form.date_from || !form.date_to) return toast.error("Fill in name and dates");
    const { error } = await supabase.from("timelapse_jobs").insert({
      name: form.name, date_from: form.date_from, date_to: form.date_to,
      fps: form.fps, codec: form.codec, state: "pending", progress: 0,
    });
    if (error) return toast.error(error.message);
    toast.success("Timelapse queued");
    setForm({ name: "", date_from: "", date_to: "", fps: 30, codec: "h264" });
    load();
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-widest text-muted-foreground">Processing</p>
        <h1 className="text-3xl font-semibold tracking-tight flex items-center gap-3"><Film className="h-7 w-7 text-primary" /> Timelapses</h1>
      </div>

      <Card className="telemetry-card grid grid-cols-1 md:grid-cols-5 gap-4 items-end">
        <Labelled label="Name"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Aug 12 night" /></Labelled>
        <Labelled label="From"><Input type="date" value={form.date_from} onChange={(e) => setForm({ ...form, date_from: e.target.value })} /></Labelled>
        <Labelled label="To"><Input type="date" value={form.date_to} onChange={(e) => setForm({ ...form, date_to: e.target.value })} /></Labelled>
        <Labelled label="FPS"><Input type="number" value={form.fps} onChange={(e) => setForm({ ...form, fps: parseInt(e.target.value || "30") })} /></Labelled>
        <Button onClick={create} className="bg-gradient-primary text-primary-foreground"><Plus className="h-4 w-4 mr-2" /> Queue</Button>
      </Card>

      <div className="space-y-3">
        {jobs.map((j) => (
          <Card key={j.id} className="telemetry-card flex items-center gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3">
                <p className="font-medium truncate">{j.name}</p>
                <StatusBadge variant={j.state === "complete" ? "ok" : j.state === "running" ? "active" : j.state === "failed" ? "error" : "warn"}>{j.state}</StatusBadge>
              </div>
              <p className="text-xs text-muted-foreground font-mono-data mt-1">
                {j.date_from} → {j.date_to} · {j.fps} fps · {j.codec.toUpperCase()} · queued {format(new Date(j.created_at), "MMM d HH:mm")}
              </p>
              <Progress value={j.progress} className="h-1 mt-3" />
            </div>
            <div className="text-right shrink-0">
              <p className="text-2xl font-mono-data">{j.progress}%</p>
              {j.output_path && <p className="text-[10px] text-muted-foreground truncate max-w-[200px]">{j.output_path}</p>}
            </div>
          </Card>
        ))}
        {jobs.length === 0 && <p className="text-sm text-muted-foreground">No timelapse jobs yet.</p>}
      </div>
    </div>
  );
}

function Labelled({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="space-y-2"><Label>{label}</Label>{children}</div>;
}
