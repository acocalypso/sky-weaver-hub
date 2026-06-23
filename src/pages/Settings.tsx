import { useEffect, useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Settings as SettingsIcon, MapPin, HardDrive, Shield } from "lucide-react";
import { toast } from "sonner";

interface S {
  id: number; observatory_name: string; latitude: number; longitude: number; timezone: string;
  storage_path: string; timelapse_path: string;
  default_capture_interval_s: number; default_image_format: string;
  retention_days: number; retention_max_disk_pct: number;
  api_enabled: boolean; startup_auto_capture: boolean;
}

export default function SettingsPage() {
  const [s, setS] = useState<S | null>(null);

  useEffect(() => {
    document.title = "Settings · AllSky Control Hub";
    supabase.from("system_settings").select("*").eq("id", 1).maybeSingle()
      .then(({ data }) => setS(data as S));
  }, []);

  async function save() {
    if (!s) return;
    const { error } = await supabase.from("system_settings").update({
      observatory_name: s.observatory_name, latitude: s.latitude, longitude: s.longitude,
      timezone: s.timezone, storage_path: s.storage_path, timelapse_path: s.timelapse_path,
      default_capture_interval_s: s.default_capture_interval_s,
      default_image_format: s.default_image_format, retention_days: s.retention_days,
      retention_max_disk_pct: s.retention_max_disk_pct, api_enabled: s.api_enabled,
      startup_auto_capture: s.startup_auto_capture,
    }).eq("id", 1);
    if (error) return toast.error(error.message);
    toast.success("Settings saved");
  }

  if (!s) return <p className="text-sm text-muted-foreground">Loading…</p>;
  const upd = (k: keyof S, v: any) => setS({ ...s, [k]: v });

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-widest text-muted-foreground">Configuration</p>
        <h1 className="text-3xl font-semibold tracking-tight flex items-center gap-3"><SettingsIcon className="h-7 w-7 text-primary" /> Settings</h1>
      </div>

      <Section icon={<MapPin className="h-4 w-4 text-primary" />} title="Location">
        <Field label="Observatory name" value={s.observatory_name} onChange={(v) => upd("observatory_name", v)} />
        <Field label="Latitude" type="number" step="0.0001" value={s.latitude.toString()} onChange={(v) => upd("latitude", parseFloat(v))} />
        <Field label="Longitude" type="number" step="0.0001" value={s.longitude.toString()} onChange={(v) => upd("longitude", parseFloat(v))} />
        <Field label="Timezone" value={s.timezone} onChange={(v) => upd("timezone", v)} placeholder="Europe/Berlin" />
      </Section>

      <Section icon={<HardDrive className="h-4 w-4 text-primary" />} title="Storage & retention">
        <Field label="Image storage path" value={s.storage_path} onChange={(v) => upd("storage_path", v)} />
        <Field label="Timelapse path" value={s.timelapse_path} onChange={(v) => upd("timelapse_path", v)} />
        <Field label="Default interval (s)" type="number" value={s.default_capture_interval_s.toString()} onChange={(v) => upd("default_capture_interval_s", parseInt(v || "0"))} />
        <Field label="Default format" value={s.default_image_format} onChange={(v) => upd("default_image_format", v)} />
        <Field label="Retention (days)" type="number" value={s.retention_days.toString()} onChange={(v) => upd("retention_days", parseInt(v || "0"))} />
        <Field label="Max disk usage (%)" type="number" value={s.retention_max_disk_pct.toString()} onChange={(v) => upd("retention_max_disk_pct", parseInt(v || "0"))} />
      </Section>

      <Section icon={<Shield className="h-4 w-4 text-primary" />} title="System">
        <Toggle label="REST API enabled" hint="Allow external apps to call /api/v1 with bearer tokens." value={s.api_enabled} onChange={(v) => upd("api_enabled", v)} />
        <Toggle label="Auto-start capture" hint="Arm the scheduler when the service boots." value={s.startup_auto_capture} onChange={(v) => upd("startup_auto_capture", v)} />
      </Section>

      <div className="flex justify-end">
        <Button onClick={save} className="bg-gradient-primary text-primary-foreground">Save settings</Button>
      </div>
    </div>
  );
}

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <Card className="telemetry-card space-y-4">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">{icon}{title}</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">{children}</div>
    </Card>
  );
}

function Field({ label, value, onChange, ...rest }: { label: string; value: string; onChange: (v: string) => void } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <Input value={value} onChange={(e) => onChange(e.target.value)} {...rest} />
    </div>
  );
}

function Toggle({ label, hint, value, onChange }: { label: string; hint: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-center justify-between p-3 rounded-md border border-border bg-muted/20 md:col-span-2">
      <div>
        <p className="text-sm font-medium">{label}</p>
        <p className="text-xs text-muted-foreground mt-0.5">{hint}</p>
      </div>
      <Switch checked={value} onCheckedChange={onChange} />
    </div>
  );
}
