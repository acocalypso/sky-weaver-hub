import { useEffect, useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/StatusBadge";
import { Camera as CameraIcon, Plus, Pencil, Camera as TestIcon } from "lucide-react";
import { toast } from "sonner";
import { triggerCapture } from "@/lib/capture";

type AdapterType = "mock" | "libcamera" | "gphoto2" | "indi" | "zwo" | "webcam" | "custom";
interface Camera { id: string; name: string; model: string | null; adapter_type: AdapterType; status: string; is_default: boolean; }
interface Settings { id?: string; camera_id: string; exposure_us: number; gain: number; resolution: string; file_format: string; white_balance: string; binning: number; }

const ADAPTERS: { value: AdapterType; label: string; hint: string }[] = [
  { value: "mock", label: "Mock", hint: "Simulated camera for development" },
  { value: "libcamera", label: "libcamera (Pi)", hint: "Raspberry Pi HQ / Camera Module v3" },
  { value: "gphoto2", label: "gPhoto2", hint: "DSLR via USB (Canon, Nikon, Sony)" },
  { value: "indi", label: "INDI", hint: "Astronomy INDI server" },
  { value: "zwo", label: "ZWO ASI", hint: "ZWO ASI USB cameras" },
  { value: "webcam", label: "V4L2 webcam", hint: "USB webcam via V4L2" },
  { value: "custom", label: "Custom", hint: "User-supplied adapter script" },
];

export default function Cameras() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [selected, setSelected] = useState<Camera | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [dlgOpen, setDlgOpen] = useState(false);
  const [editing, setEditing] = useState<Camera | null>(null);

  useEffect(() => { document.title = "Cameras · AllSky Control Hub"; load(); }, []);

  async function load() {
    const { data } = await supabase.from("cameras").select("*").order("created_at");
    setCameras((data ?? []) as Camera[]);
    if (data?.length && !selected) await pick(data[0] as Camera);
  }

  async function pick(c: Camera) {
    setSelected(c);
    const { data } = await supabase.from("camera_settings").select("*").eq("camera_id", c.id).maybeSingle();
    setSettings((data as Settings) ?? { camera_id: c.id, exposure_us: 1_000_000, gain: 100, resolution: "1920x1080", file_format: "jpg", white_balance: "auto", binning: 1 });
  }

  async function saveCamera(form: Partial<Camera>) {
    if (editing?.id) {
      const { error } = await supabase.from("cameras").update(form).eq("id", editing.id);
      if (error) return toast.error(error.message);
      toast.success("Camera updated");
    } else {
      const { data, error } = await supabase.from("cameras").insert({
        name: form.name ?? "New camera", model: form.model ?? null,
        adapter_type: (form.adapter_type ?? "mock") as AdapterType, status: "unknown",
      }).select().single();
      if (error) return toast.error(error.message);
      await supabase.from("camera_settings").insert({ camera_id: data!.id });
      toast.success("Camera created");
    }
    setDlgOpen(false); setEditing(null); await load();
  }

  async function saveSettings() {
    if (!settings || !selected) return;
    const payload = { ...settings, camera_id: selected.id };
    const { error } = await supabase.from("camera_settings").upsert(payload, { onConflict: "camera_id" });
    if (error) return toast.error(error.message);
    toast.success("Settings saved");
  }

  async function runTest() {
    if (!selected) return;
    toast.message("Test shot queued…");
    try { await triggerCapture({ camera_id: selected.id, type: "test" }); toast.success("Test image captured"); }
    catch (e: any) { toast.error(e.message ?? "Capture failed"); }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground">Hardware</p>
          <h1 className="text-3xl font-semibold tracking-tight">Cameras</h1>
        </div>
        <Dialog open={dlgOpen} onOpenChange={setDlgOpen}>
          <DialogTrigger asChild>
            <Button onClick={() => setEditing(null)}><Plus className="h-4 w-4 mr-2" /> New camera</Button>
          </DialogTrigger>
          <CameraDialog editing={editing} onSave={saveCamera} />
        </Dialog>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-6">
        <Card className="telemetry-card p-2 space-y-1">
          {cameras.map((c) => (
            <button key={c.id} onClick={() => pick(c)}
              className={`w-full text-left p-3 rounded-md border ${selected?.id === c.id ? "border-primary bg-primary/5" : "border-transparent hover:bg-muted/40"}`}>
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium flex items-center gap-2"><CameraIcon className="h-4 w-4 text-primary" />{c.name}</span>
                {c.is_default && <StatusBadge variant="active">default</StatusBadge>}
              </div>
              <div className="mt-1 text-xs text-muted-foreground font-mono-data">{c.adapter_type} · {c.status}</div>
            </button>
          ))}
          {cameras.length === 0 && <p className="p-3 text-sm text-muted-foreground">No cameras yet.</p>}
        </Card>

        {selected && settings && (
          <Card className="telemetry-card space-y-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-xl font-semibold">{selected.name}</h2>
                <p className="text-xs text-muted-foreground font-mono-data mt-1">{selected.model ?? "—"} · adapter {selected.adapter_type}</p>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={runTest}><TestIcon className="h-4 w-4 mr-2" /> Test shot</Button>
                <Button variant="outline" size="sm" onClick={() => { setEditing(selected); setDlgOpen(true); }}><Pencil className="h-4 w-4 mr-2" /> Edit</Button>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Field label="Exposure (seconds)" type="number" step="0.1"
                value={(settings.exposure_us / 1_000_000).toString()}
                onChange={(v) => setSettings({ ...settings, exposure_us: Math.round(parseFloat(v || "0") * 1_000_000) })} />
              <Field label="Gain" type="number" value={settings.gain.toString()}
                onChange={(v) => setSettings({ ...settings, gain: parseInt(v || "0") })} />
              <Field label="Resolution" value={settings.resolution} onChange={(v) => setSettings({ ...settings, resolution: v })} placeholder="1920x1080" />
              <div className="space-y-2">
                <Label>File format</Label>
                <Select value={settings.file_format} onValueChange={(v) => setSettings({ ...settings, file_format: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {["jpg", "png", "tif", "fits", "raw"].map((f) => <SelectItem key={f} value={f}>{f.toUpperCase()}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>White balance</Label>
                <Select value={settings.white_balance} onValueChange={(v) => setSettings({ ...settings, white_balance: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {["auto", "daylight", "tungsten", "fluorescent", "cloudy", "manual"].map((f) => <SelectItem key={f} value={f}>{f}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <Field label="Binning" type="number" value={settings.binning.toString()}
                onChange={(v) => setSettings({ ...settings, binning: Math.max(1, parseInt(v || "1")) })} />
            </div>

            <div className="flex justify-end gap-2">
              <Button onClick={saveSettings} className="bg-gradient-primary text-primary-foreground">Save settings</Button>
            </div>
          </Card>
        )}
      </div>
    </div>
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

function CameraDialog({ editing, onSave }: { editing: Camera | null; onSave: (f: Partial<Camera>) => void }) {
  const [name, setName] = useState(editing?.name ?? "");
  const [model, setModel] = useState(editing?.model ?? "");
  const [adapter, setAdapter] = useState<AdapterType>(editing?.adapter_type ?? "mock");
  useEffect(() => { setName(editing?.name ?? ""); setModel(editing?.model ?? ""); setAdapter(editing?.adapter_type ?? "mock"); }, [editing]);
  const hint = ADAPTERS.find((a) => a.value === adapter)?.hint;
  return (
    <DialogContent>
      <DialogHeader><DialogTitle>{editing ? "Edit camera" : "New camera"}</DialogTitle></DialogHeader>
      <div className="space-y-4">
        <Field label="Name" value={name} onChange={setName} placeholder="Roof All-Sky" />
        <Field label="Model" value={model} onChange={setModel} placeholder="ZWO ASI224MC" />
        <div className="space-y-2">
          <Label>Adapter</Label>
          <Select value={adapter} onValueChange={(v) => setAdapter(v as AdapterType)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>{ADAPTERS.map((a) => <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>)}</SelectContent>
          </Select>
          {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
        </div>
      </div>
      <DialogFooter>
        <Button onClick={() => onSave({ name, model: model || null, adapter_type: adapter })} className="bg-gradient-primary text-primary-foreground">
          {editing ? "Save" : "Create"}
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}
