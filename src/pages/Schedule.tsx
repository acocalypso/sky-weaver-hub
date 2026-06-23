import { useEffect, useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { CalendarClock, CloudSun } from "lucide-react";
import { toast } from "sonner";

interface Schedule {
  id?: string;
  camera_id: string | null;
  enabled: boolean;
  start_condition: string;
  end_condition: string;
  start_time: string | null;
  end_time: string | null;
  interval_seconds: number;
  ramping: { enabled: boolean; min_exposure_us: number; max_exposure_us: number };
  weather_safe: boolean;
  daytime_protect: boolean;
}

const CONDITIONS = [
  { value: "civil_twilight", label: "Civil twilight (sun < -6°)" },
  { value: "nautical_twilight", label: "Nautical twilight (sun < -12°)" },
  { value: "astronomical_twilight", label: "Astronomical twilight (sun < -18°)" },
  { value: "sunset", label: "Sunset / sunrise" },
  { value: "fixed_time", label: "Fixed clock time" },
];

export default function Schedule() {
  const [s, setS] = useState<Schedule | null>(null);

  useEffect(() => {
    document.title = "Schedule · AllSky Control Hub";
    (async () => {
      const { data } = await supabase.from("capture_schedule").select("*").limit(1).maybeSingle();
      if (data) setS(data as unknown as Schedule);
    })();
  }, []);

  async function save() {
    if (!s) return;
    const { error } = await supabase.from("capture_schedule").update({
      enabled: s.enabled, start_condition: s.start_condition, end_condition: s.end_condition,
      start_time: s.start_time, end_time: s.end_time, interval_seconds: s.interval_seconds,
      ramping: s.ramping, weather_safe: s.weather_safe, daytime_protect: s.daytime_protect,
    }).eq("id", s.id!);
    if (error) return toast.error(error.message);
    toast.success("Schedule saved");
    await supabase.from("realtime_events").insert({ type: "schedule_updated", payload: { id: s.id } });
  }

  if (!s) return <p className="text-sm text-muted-foreground">Loading…</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground">Automation</p>
          <h1 className="text-3xl font-semibold tracking-tight">Capture schedule</h1>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">{s.enabled ? "Active" : "Paused"}</span>
          <Switch checked={s.enabled} onCheckedChange={(v) => setS({ ...s, enabled: v })} />
        </div>
      </div>

      <Card className="telemetry-card space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-2">
            <Label className="flex items-center gap-2"><CalendarClock className="h-4 w-4 text-primary" /> Start condition</Label>
            <Select value={s.start_condition} onValueChange={(v) => setS({ ...s, start_condition: v })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>{CONDITIONS.map((c) => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}</SelectContent>
            </Select>
            {s.start_condition === "fixed_time" && (
              <Input type="time" value={s.start_time ?? ""} onChange={(e) => setS({ ...s, start_time: e.target.value })} />
            )}
          </div>
          <div className="space-y-2">
            <Label className="flex items-center gap-2"><CalendarClock className="h-4 w-4 text-accent" /> End condition</Label>
            <Select value={s.end_condition} onValueChange={(v) => setS({ ...s, end_condition: v })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>{CONDITIONS.map((c) => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}</SelectContent>
            </Select>
            {s.end_condition === "fixed_time" && (
              <Input type="time" value={s.end_time ?? ""} onChange={(e) => setS({ ...s, end_time: e.target.value })} />
            )}
          </div>
        </div>

        <div>
          <Label>Interval between captures: <span className="font-mono-data text-foreground">{s.interval_seconds}s</span></Label>
          <Slider min={5} max={600} step={5} value={[s.interval_seconds]}
            onValueChange={([v]) => setS({ ...s, interval_seconds: v })} className="mt-3" />
        </div>

        <Card className="bg-muted/30 border-muted p-4 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Exposure ramping</p>
              <p className="text-xs text-muted-foreground">Smoothly adjust exposure from twilight to full dark.</p>
            </div>
            <Switch checked={s.ramping.enabled} onCheckedChange={(v) => setS({ ...s, ramping: { ...s.ramping, enabled: v } })} />
          </div>
          {s.ramping.enabled && (
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Min exposure (s)</Label>
                <Input type="number" step="0.001" value={(s.ramping.min_exposure_us / 1_000_000).toString()}
                  onChange={(e) => setS({ ...s, ramping: { ...s.ramping, min_exposure_us: Math.round(parseFloat(e.target.value || "0") * 1_000_000) } })} />
              </div>
              <div className="space-y-2">
                <Label>Max exposure (s)</Label>
                <Input type="number" step="0.1" value={(s.ramping.max_exposure_us / 1_000_000).toString()}
                  onChange={(e) => setS({ ...s, ramping: { ...s.ramping, max_exposure_us: Math.round(parseFloat(e.target.value || "0") * 1_000_000) } })} />
              </div>
            </div>
          )}
        </Card>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <ToggleRow label="Weather-safe" hint="Pause capture if weather sensor reports unsafe."
            value={s.weather_safe} onChange={(v) => setS({ ...s, weather_safe: v })} icon={<CloudSun className="h-4 w-4 text-accent" />} />
          <ToggleRow label="Daytime protect" hint="Refuse to capture when the sun is up."
            value={s.daytime_protect} onChange={(v) => setS({ ...s, daytime_protect: v })} />
        </div>

        <div className="flex justify-end">
          <Button onClick={save} className="bg-gradient-primary text-primary-foreground">Save schedule</Button>
        </div>
      </Card>
    </div>
  );
}

function ToggleRow({ label, hint, value, onChange, icon }: { label: string; hint: string; value: boolean; onChange: (v: boolean) => void; icon?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between p-3 rounded-md border border-border bg-muted/20">
      <div>
        <p className="text-sm font-medium flex items-center gap-2">{icon}{label}</p>
        <p className="text-xs text-muted-foreground mt-0.5">{hint}</p>
      </div>
      <Switch checked={value} onCheckedChange={onChange} />
    </div>
  );
}
