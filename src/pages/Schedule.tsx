import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { StatusBadge } from "@/components/StatusBadge";
import { SkyApi, type SchedulePreview, type ScheduleRow } from "@/lib/api";
import { CalendarClock, Moon, Sunrise } from "lucide-react";
import { toast } from "sonner";
import { format, formatDistanceToNow } from "date-fns";

const startModeOptions = [
  { value: "sun_angle", label: "Sun altitude" },
  { value: "sunset", label: "Sunset" },
  { value: "civil_dusk", label: "Civil dusk" },
  { value: "nautical_dusk", label: "Nautical dusk" },
  { value: "astronomical_dusk", label: "Astronomical dusk" },
  { value: "fixed", label: "Fixed clock time" },
  { value: "manual", label: "Manual" },
];

const endModeOptions = [
  { value: "sun_angle", label: "Sun altitude" },
  { value: "sunrise", label: "Sunrise" },
  { value: "civil_dawn", label: "Civil dawn" },
  { value: "nautical_dawn", label: "Nautical dawn" },
  { value: "astronomical_dawn", label: "Astronomical dawn" },
  { value: "fixed", label: "Fixed clock time" },
  { value: "manual", label: "Manual" },
];

export default function Schedule() {
  const [s, setS] = useState<ScheduleRow | null>(null);
  const [preview, setPreview] = useState<SchedulePreview | null>(null);
  const [observatory, setObservatory] = useState<Record<string, any> | null>(null);

  useEffect(() => {
    document.title = "Schedule - Sky Weaver Hub";
    Promise.all([SkyApi.schedule(), SkyApi.settings()])
      .then(([schedule, settings]) => {
        setObservatory(settings.observatory ?? null);
        setS(schedule);
        return SkyApi.schedulePreview(schedule);
      })
      .then(setPreview)
      .catch((e) => toast.error(e.message));
  }, []);

  useEffect(() => {
    if (!s) return;
    const timer = window.setTimeout(() => {
      SkyApi.schedulePreview(s).then(setPreview).catch(() => undefined);
    }, 350);
    return () => window.clearTimeout(timer);
  }, [s]);

  async function save() {
    if (!s) return;
    try {
      const saved = await SkyApi.putSchedule(s);
      setS(saved);
      setPreview(await SkyApi.schedulePreview(saved));
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
      <Card className="telemetry-card">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div className="space-y-1">
            <p className="text-xs uppercase tracking-widest text-muted-foreground">Tonight window</p>
            <div className="flex items-center gap-2">
              <StatusBadge variant={preview?.active ? "active" : s.enabled ? "idle" : "warn"} pulse={preview?.active}>{preview?.active ? "capturing window" : s.enabled ? "waiting" : "disabled"}</StatusBadge>
              <span className="text-xs text-muted-foreground font-mono-data">{preview?.timezone ?? s.timezone}</span>
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 text-xs font-mono-data">
            <PreviewStat icon={<Moon className="h-3.5 w-3.5" />} label="Start" value={formatPreview(preview?.window_start)} />
            <PreviewStat icon={<Sunrise className="h-3.5 w-3.5" />} label="End" value={formatPreview(preview?.window_end)} />
            <PreviewStat icon={<CalendarClock className="h-3.5 w-3.5" />} label="Next" value={preview?.next_transition_at ? `${preview.next_state} ${formatDistanceToNow(new Date(preview.next_transition_at), { addSuffix: true })}` : "-"} />
            <PreviewStat icon={<CalendarClock className="h-3.5 w-3.5" />} label="Capture" value={formatNextCapture(preview)} />
          </div>
        </div>
      </Card>
      <Card className="telemetry-card space-y-6">
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={() => setS({ ...s, start_mode: "nautical_dusk", end_mode: "sunrise" })}>Nautical dusk to sunrise</Button>
          <Button variant="outline" size="sm" onClick={() => setS({ ...s, start_mode: "sunset", end_mode: "sunrise" })}>Sunset to sunrise</Button>
          <Button variant="outline" size="sm" onClick={() => setS({ ...s, start_mode: "astronomical_dusk", end_mode: "astronomical_dawn" })}>Astronomical night</Button>
          {observatory && <Button variant="outline" size="sm" onClick={() => setS({ ...s, timezone: String(observatory.timezone ?? s.timezone), latitude: Number(observatory.latitude ?? s.latitude), longitude: Number(observatory.longitude ?? s.longitude) })}>Use observatory</Button>}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <ModeSelect label="Start mode" value={s.start_mode} options={startModeOptions} onChange={(v) => setS({ ...s, start_mode: v })} />
          <ModeSelect label="End mode" value={s.end_mode} options={endModeOptions} onChange={(v) => setS({ ...s, end_mode: v })} />
          {s.start_mode === "fixed" && <Field label="Fixed start time" type="time" value={s.fixed_start_time ?? "18:00"} onChange={(v) => setS({ ...s, fixed_start_time: v })} />}
          {s.end_mode === "fixed" && <Field label="Fixed end time" type="time" value={s.fixed_end_time ?? "06:00"} onChange={(v) => setS({ ...s, fixed_end_time: v })} />}
          {s.start_mode === "sun_angle" && <Field label="Start sun altitude" type="number" step="0.1" value={String(s.start_sun_angle ?? s.sun_angle)} onChange={(v) => setS({ ...s, start_sun_angle: Number(v), sun_angle: Number(v) })} />}
          {s.end_mode === "sun_angle" && <Field label="End sun altitude" type="number" step="0.1" value={String(s.end_sun_angle ?? s.sun_angle)} onChange={(v) => setS({ ...s, end_sun_angle: Number(v) })} />}
          <Field label="Latitude" type="number" step="0.0001" value={String(s.latitude)} onChange={(v) => setS({ ...s, latitude: Number(v) })} />
          <Field label="Longitude" type="number" step="0.0001" value={String(s.longitude)} onChange={(v) => setS({ ...s, longitude: Number(v) })} />
          <Field label="Timezone" value={s.timezone} onChange={(v) => setS({ ...s, timezone: v })} />
        </div>
        <div><Label>Interval between captures: <span className="font-mono-data text-foreground">{s.interval_seconds}s</span></Label><Slider min={5} max={600} step={5} value={[s.interval_seconds]} onValueChange={([v]) => setS({ ...s, interval_seconds: v })} className="mt-3" /></div>
        <div className="flex items-center justify-between p-3 rounded-md border border-border bg-muted/20"><div><p className="text-sm font-medium">Exposure ramping</p><p className="text-xs text-muted-foreground mt-0.5">Worker will smooth exposure changes during twilight.</p></div><Switch checked={s.exposure_ramping_enabled} onCheckedChange={(v) => setS({ ...s, exposure_ramping_enabled: v })} /></div>
        <div className="flex justify-end"><Button onClick={save} className="bg-gradient-primary text-primary-foreground">Save schedule</Button></div>
      </Card>
    </div>
  );
}

function ModeSelect({ label, value, options, onChange }: { label: string; value: string; options: { value: string; label: string }[]; onChange: (v: string) => void }) {
  return <div className="space-y-2"><Label className="flex items-center gap-2"><CalendarClock className="h-4 w-4 text-primary" /> {label}</Label><Select value={value} onValueChange={onChange}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{options.map((option) => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}</SelectContent></Select></div>;
}

function Field({ label, value, onChange, ...rest }: { label: string; value: string; onChange: (v: string) => void } & React.InputHTMLAttributes<HTMLInputElement>) {
  return <div className="space-y-2"><Label>{label}</Label><Input value={value} onChange={(e) => onChange(e.target.value)} {...rest} /></div>;
}

function PreviewStat({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return <div className="rounded-md bg-muted/40 border border-border px-3 py-2 min-w-0"><p className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-muted-foreground">{icon}{label}</p><p className="truncate mt-1 text-foreground">{value}</p></div>;
}

function formatPreview(value?: string | null) {
  if (!value) return "-";
  return format(new Date(value), "MMM d HH:mm");
}

function formatNextCapture(preview?: SchedulePreview | null) {
  if (!preview) return "-";
  if (!preview.capture_enabled) return `${preview.capture_mode ?? "capture"} disabled`;
  if (preview.capture_due) return `${preview.capture_mode ?? "capture"} due now`;
  if (!preview.next_capture_due_at) return "-";
  return `${preview.capture_mode ?? "capture"} ${formatDistanceToNow(new Date(preview.next_capture_due_at), { addSuffix: true })}`;
}
