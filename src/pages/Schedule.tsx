import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { SkyApi, type ScheduleRow } from "@/lib/api";
import { CalendarClock } from "lucide-react";
import { toast } from "sonner";

export default function Schedule() {
  const [s, setS] = useState<ScheduleRow | null>(null);

  useEffect(() => {
    document.title = "Schedule - Sky Weaver Hub";
    SkyApi.schedule().then(setS).catch((e) => toast.error(e.message));
  }, []);

  async function save() {
    if (!s) return;
    try {
      await SkyApi.putSchedule(s);
      toast.success("Schedule saved");
    } catch (e: any) {
      toast.error(e.message ?? "Save failed");
    }
  }

  if (!s) return <p className="text-sm text-muted-foreground">Loading...</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div><p className="text-xs uppercase tracking-widest text-muted-foreground">Automation</p><h1 className="text-3xl font-semibold tracking-tight">Capture schedule</h1></div>
        <div className="flex items-center gap-3"><span className="text-xs text-muted-foreground">{s.enabled ? "Active" : "Paused"}</span><Switch checked={s.enabled} onCheckedChange={(v) => setS({ ...s, enabled: v })} /></div>
      </div>
      <Card className="telemetry-card space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <ModeSelect label="Start mode" value={s.start_mode} onChange={(v) => setS({ ...s, start_mode: v })} />
          <ModeSelect label="End mode" value={s.end_mode} onChange={(v) => setS({ ...s, end_mode: v })} />
          <Field label="Latitude" type="number" step="0.0001" value={String(s.latitude)} onChange={(v) => setS({ ...s, latitude: Number(v) })} />
          <Field label="Longitude" type="number" step="0.0001" value={String(s.longitude)} onChange={(v) => setS({ ...s, longitude: Number(v) })} />
          <Field label="Timezone" value={s.timezone} onChange={(v) => setS({ ...s, timezone: v })} />
          <Field label="Sun angle" type="number" value={String(s.sun_angle)} onChange={(v) => setS({ ...s, sun_angle: Number(v) })} />
        </div>
        <div><Label>Interval between captures: <span className="font-mono-data text-foreground">{s.interval_seconds}s</span></Label><Slider min={5} max={600} step={5} value={[s.interval_seconds]} onValueChange={([v]) => setS({ ...s, interval_seconds: v })} className="mt-3" /></div>
        <div className="flex items-center justify-between p-3 rounded-md border border-border bg-muted/20"><div><p className="text-sm font-medium">Exposure ramping</p><p className="text-xs text-muted-foreground mt-0.5">Worker will smooth exposure changes during twilight.</p></div><Switch checked={s.exposure_ramping_enabled} onCheckedChange={(v) => setS({ ...s, exposure_ramping_enabled: v })} /></div>
        <div className="flex justify-end"><Button onClick={save} className="bg-gradient-primary text-primary-foreground">Save schedule</Button></div>
      </Card>
    </div>
  );
}

function ModeSelect({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return <div className="space-y-2"><Label className="flex items-center gap-2"><CalendarClock className="h-4 w-4 text-primary" /> {label}</Label><Select value={value} onValueChange={onChange}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="sun_angle">Sun angle</SelectItem><SelectItem value="fixed">Fixed clock time</SelectItem><SelectItem value="manual">Manual</SelectItem></SelectContent></Select></div>;
}

function Field({ label, value, onChange, ...rest }: { label: string; value: string; onChange: (v: string) => void } & React.InputHTMLAttributes<HTMLInputElement>) {
  return <div className="space-y-2"><Label>{label}</Label><Input value={value} onChange={(e) => onChange(e.target.value)} {...rest} /></div>;
}
