import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { SkyApi } from "@/lib/api";
import { Settings as SettingsIcon, MapPin, HardDrive, Shield } from "lucide-react";
import { toast } from "sonner";

export default function SettingsPage() {
  const [values, setValues] = useState<Record<string, any> | null>(null);

  useEffect(() => {
    document.title = "Settings - Sky Weaver Hub";
    SkyApi.settings().then(setValues).catch((e) => toast.error(e.message));
  }, []);

  if (!values) return <p className="text-sm text-muted-foreground">Loading...</p>;
  const observatory = values.observatory ?? {};
  const storage = values.storage ?? {};
  const publicPage = values.public_page ?? {};
  const security = values.security ?? {};
  const updateGroup = (group: string, patch: any) => setValues({ ...values, [group]: { ...(values[group] ?? {}), ...patch } });

  async function save() {
    if (!values) return;
    try {
      await SkyApi.patchSettings(values);
      toast.success("Settings saved");
    } catch (e: any) {
      toast.error(e.message ?? "Save failed");
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-widest text-muted-foreground">Configuration</p>
        <h1 className="text-3xl font-semibold tracking-tight flex items-center gap-3"><SettingsIcon className="h-7 w-7 text-primary" /> Settings</h1>
      </div>

      <Section icon={<MapPin className="h-4 w-4 text-primary" />} title="Location">
        <Field label="Observatory name" value={observatory.name ?? ""} onChange={(v) => updateGroup("observatory", { name: v })} />
        <Field label="Latitude" type="number" step="0.0001" value={String(observatory.latitude ?? 0)} onChange={(v) => updateGroup("observatory", { latitude: Number(v) })} />
        <Field label="Longitude" type="number" step="0.0001" value={String(observatory.longitude ?? 0)} onChange={(v) => updateGroup("observatory", { longitude: Number(v) })} />
        <Field label="Timezone" value={observatory.timezone ?? "UTC"} onChange={(v) => updateGroup("observatory", { timezone: v })} />
      </Section>

      <Section icon={<HardDrive className="h-4 w-4 text-primary" />} title="Storage and retention">
        <Field label="Image storage path" value={storage.images ?? "./data/images"} onChange={(v) => updateGroup("storage", { images: v })} />
        <Field label="Video storage path" value={storage.videos ?? "./data/videos"} onChange={(v) => updateGroup("storage", { videos: v })} />
        <Field label="Retention days" type="number" value={String(storage.retention_days ?? 30)} onChange={(v) => updateGroup("storage", { retention_days: Number(v) })} />
        <Field label="Minimum free GB" type="number" value={String(storage.min_free_gb ?? 2)} onChange={(v) => updateGroup("storage", { min_free_gb: Number(v) })} />
      </Section>

      <Section icon={<Shield className="h-4 w-4 text-primary" />} title="Public and API">
        <Toggle label="Public page enabled" hint="Expose /public without admin controls." value={Boolean(publicPage.enabled)} onChange={(v) => updateGroup("public_page", { enabled: v })} />
        <Toggle label="Iframe mode enabled" hint="Allow an embeddable read-only public sky view." value={Boolean(publicPage.iframe_enabled)} onChange={(v) => updateGroup("public_page", { iframe_enabled: v })} />
        <Field label="CORS origins" value={(security.cors_origins ?? []).join(",")} onChange={(v) => updateGroup("security", { cors_origins: v.split(",").map((x) => x.trim()).filter(Boolean) })} />
        <Toggle label="First setup required" hint="Installer should force a password change before unattended use." value={Boolean(security.first_setup_required)} onChange={(v) => updateGroup("security", { first_setup_required: v })} />
      </Section>

      <div className="flex justify-end">
        <Button onClick={save} className="bg-gradient-primary text-primary-foreground">Save settings</Button>
      </div>
    </div>
  );
}

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return <Card className="telemetry-card space-y-4"><h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">{icon}{title}</h2><div className="grid grid-cols-1 md:grid-cols-2 gap-4">{children}</div></Card>;
}

function Field({ label, value, onChange, ...rest }: { label: string; value: string; onChange: (v: string) => void } & React.InputHTMLAttributes<HTMLInputElement>) {
  return <div className="space-y-2"><Label>{label}</Label><Input value={value} onChange={(e) => onChange(e.target.value)} {...rest} /></div>;
}

function Toggle({ label, hint, value, onChange }: { label: string; hint: string; value: boolean; onChange: (v: boolean) => void }) {
  return <div className="flex items-center justify-between p-3 rounded-md border border-border bg-muted/20"><div><p className="text-sm font-medium">{label}</p><p className="text-xs text-muted-foreground mt-0.5">{hint}</p></div><Switch checked={value} onCheckedChange={onChange} /></div>;
}
