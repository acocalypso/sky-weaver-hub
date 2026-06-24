import { useCallback, useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/StatusBadge";
import { SkyApi, type CameraProfile, type CameraRow, type DetectedCamera } from "@/lib/api";
import { Camera as CameraIcon, Plus, Pencil, Camera as TestIcon, Radar } from "lucide-react";
import { toast } from "sonner";

type AdapterType = "mock" | "rpicam" | "libcamera" | "gphoto2" | "indi" | "zwo" | "v4l2" | "custom_command";

const ADAPTERS: { value: AdapterType; label: string; hint: string }[] = [
  { value: "mock", label: "Mock", hint: "Synthetic camera for development and CI" },
  { value: "rpicam", label: "rpicam/libcamera", hint: "Raspberry Pi HQ, Camera Module 3, Arducam libcamera devices" },
  { value: "zwo", label: "ZWO ASI", hint: "SDK boundary placeholder with actionable errors" },
  { value: "gphoto2", label: "gPhoto2", hint: "DSLR/mirrorless via USB" },
  { value: "v4l2", label: "V4L2 webcam", hint: "USB webcams via ffmpeg/V4L2" },
  { value: "indi", label: "INDI", hint: "Future INDI server adapter" },
  { value: "custom_command", label: "Custom command", hint: "Disabled until sandbox configuration is explicit" },
];

export default function Cameras() {
  const [cameras, setCameras] = useState<CameraRow[]>([]);
  const [detected, setDetected] = useState<DetectedCamera[]>([]);
  const [profiles, setProfiles] = useState<CameraProfile[]>([]);
  const [selected, setSelected] = useState<CameraRow | null>(null);
  const [settings, setSettings] = useState<Record<string, any>>({});
  const [dlgOpen, setDlgOpen] = useState(false);
  const [editing, setEditing] = useState<CameraRow | null>(null);
  const selectedId = selected?.id;

  const pick = useCallback((camera: CameraRow, profs = profiles) => {
    setSelected(camera);
    setSettings(profs.find((p) => p.camera_id === camera.id && p.mode === "nighttime")?.settings ?? {});
  }, [profiles]);

  const load = useCallback(async () => {
    const [cams, profs] = await Promise.all([SkyApi.cameras(), SkyApi.cameraProfiles()]);
    setCameras(cams);
    setProfiles(profs);
    const first = selectedId ? cams.find((c) => c.id === selectedId) : cams[0];
    if (first) {
      setSelected(first);
      setSettings(profs.find((p) => p.camera_id === first.id && p.mode === "nighttime")?.settings ?? {});
    }
  }, [selectedId]);

  useEffect(() => { document.title = "Cameras - Sky Weaver Hub"; load(); }, [load]);

  async function runDetect() {
    try {
      const found = await SkyApi.detectCameras();
      setDetected(found);
      toast.success(`${found.length} camera candidate${found.length === 1 ? "" : "s"} found`);
    } catch (e: any) {
      toast.error(e.message ?? "Detection failed");
    }
  }

  async function saveCamera(form: { name: string; model: string | null; adapter: AdapterType; is_primary: boolean }) {
    try {
      if (editing?.id) await SkyApi.patchCamera(editing.id, form);
      else await SkyApi.createCamera({ ...form, enabled: true });
      toast.success(editing ? "Camera updated" : "Camera created");
      setDlgOpen(false); setEditing(null); await load();
    } catch (e: any) {
      toast.error(e.message ?? "Save failed");
    }
  }

  async function saveSettings() {
    const profile = profiles.find((p) => p.camera_id === selected?.id && p.mode === "nighttime");
    if (!profile) return toast.error("No nighttime profile exists for this camera yet");
    try {
      await SkyApi.patchProfile(profile.id, settings);
      toast.success("Night profile saved");
      await load();
    } catch (e: any) {
      toast.error(e.message ?? "Settings save failed");
    }
  }

  async function runTest() {
    if (!selected) return;
    try {
      await SkyApi.testShot({ camera_id: selected.id, exposure_ms: Number(settings.manual_exposure_ms ?? 1000), gain: Number(settings.gain ?? 1), mode: "manual" });
      toast.success("Test shot queued");
    } catch (e: any) {
      toast.error(e.message ?? "Capture failed");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground">Hardware</p>
          <h1 className="text-3xl font-semibold tracking-tight">Cameras</h1>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={runDetect}><Radar className="h-4 w-4 mr-2" /> Detect</Button>
          <Dialog open={dlgOpen} onOpenChange={setDlgOpen}>
            <DialogTrigger asChild><Button onClick={() => setEditing(null)}><Plus className="h-4 w-4 mr-2" /> New camera</Button></DialogTrigger>
            <CameraDialog editing={editing} onSave={saveCamera} />
          </Dialog>
        </div>
      </div>

      {detected.length > 0 && (
        <Card className="telemetry-card space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Detected hardware</h2>
          {detected.map((d) => <p key={`${d.backend}-${d.id}`} className="text-sm font-mono-data">{d.backend} - {d.name} - {d.model ?? d.id}</p>)}
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-6">
        <Card className="telemetry-card p-2 space-y-1">
          {cameras.map((c) => (
            <button key={c.id} onClick={() => pick(c)} className={`w-full text-left p-3 rounded-md border ${selected?.id === c.id ? "border-primary bg-primary/5" : "border-transparent hover:bg-muted/40"}`}>
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium flex items-center gap-2"><CameraIcon className="h-4 w-4 text-primary" />{c.name}</span>
                {c.is_primary && <StatusBadge variant="active">primary</StatusBadge>}
              </div>
              <div className="mt-1 text-xs text-muted-foreground font-mono-data">{c.adapter} - {c.enabled ? "enabled" : "disabled"}</div>
            </button>
          ))}
          {cameras.length === 0 && <p className="p-3 text-sm text-muted-foreground">No cameras yet.</p>}
        </Card>

        {selected && (
          <Card className="telemetry-card space-y-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-xl font-semibold">{selected.name}</h2>
                <p className="text-xs text-muted-foreground font-mono-data mt-1">{selected.model ?? "-"} - adapter {selected.adapter}</p>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={runTest}><TestIcon className="h-4 w-4 mr-2" /> Test shot</Button>
                <Button variant="outline" size="sm" onClick={() => { setEditing(selected); setDlgOpen(true); }}><Pencil className="h-4 w-4 mr-2" /> Edit</Button>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Field label="Manual exposure (ms)" type="number" value={String(settings.manual_exposure_ms ?? 1000)} onChange={(v) => setSettings({ ...settings, manual_exposure_ms: Number(v) })} />
              <Field label="Gain" type="number" value={String(settings.gain ?? 1)} onChange={(v) => setSettings({ ...settings, gain: Number(v) })} />
              <Field label="Max auto exposure (ms)" type="number" value={String(settings.max_auto_exposure_ms ?? 30000)} onChange={(v) => setSettings({ ...settings, max_auto_exposure_ms: Number(v) })} />
              <Field label="Mean target" type="number" step="0.01" value={String(settings.mean_target ?? 0.28)} onChange={(v) => setSettings({ ...settings, mean_target: Number(v) })} />
              <Field label="Red balance" type="number" step="0.1" value={String(settings.red_balance ?? 1)} onChange={(v) => setSettings({ ...settings, red_balance: Number(v) })} />
              <Field label="Blue balance" type="number" step="0.1" value={String(settings.blue_balance ?? 1)} onChange={(v) => setSettings({ ...settings, blue_balance: Number(v) })} />
            </div>

            <div className="flex justify-end">
              <Button onClick={saveSettings} className="bg-gradient-primary text-primary-foreground">Save night profile</Button>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}

function Field({ label, value, onChange, ...rest }: { label: string; value: string; onChange: (v: string) => void } & React.InputHTMLAttributes<HTMLInputElement>) {
  return <div className="space-y-2"><Label>{label}</Label><Input value={value} onChange={(e) => onChange(e.target.value)} {...rest} /></div>;
}

function CameraDialog({ editing, onSave }: { editing: CameraRow | null; onSave: (f: { name: string; model: string | null; adapter: AdapterType; is_primary: boolean }) => void }) {
  const [name, setName] = useState(editing?.name ?? "");
  const [model, setModel] = useState(editing?.model ?? "");
  const [adapter, setAdapter] = useState<AdapterType>((editing?.adapter as AdapterType) ?? "mock");
  const [primary, setPrimary] = useState(Boolean(editing?.is_primary));
  useEffect(() => { setName(editing?.name ?? ""); setModel(editing?.model ?? ""); setAdapter((editing?.adapter as AdapterType) ?? "mock"); setPrimary(Boolean(editing?.is_primary)); }, [editing]);
  const hint = ADAPTERS.find((a) => a.value === adapter)?.hint;
  return (
    <DialogContent>
      <DialogHeader><DialogTitle>{editing ? "Edit camera" : "New camera"}</DialogTitle></DialogHeader>
      <div className="space-y-4">
        <Field label="Name" value={name} onChange={setName} placeholder="Roof All-Sky" />
        <Field label="Model" value={model} onChange={setModel} placeholder="IMX477 / IMX708 / ASI224MC" />
        <div className="space-y-2">
          <Label>Adapter</Label>
          <Select value={adapter} onValueChange={(v) => setAdapter(v as AdapterType)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>{ADAPTERS.map((a) => <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>)}</SelectContent>
          </Select>
          {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
        </div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={primary} onChange={(e) => setPrimary(e.target.checked)} /> Primary camera</label>
      </div>
      <DialogFooter>
        <Button onClick={() => onSave({ name, model: model || null, adapter, is_primary: primary })} className="bg-gradient-primary text-primary-foreground">{editing ? "Save" : "Create"}</Button>
      </DialogFooter>
    </DialogContent>
  );
}
