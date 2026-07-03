import { useCallback, useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/StatusBadge";
import { ConfigHelp, ConfigLabel } from "@/components/ConfigHelp";
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
  const [profileMode, setProfileMode] = useState<"daytime" | "nighttime">("nighttime");
  const [settings, setSettings] = useState<Record<string, any>>({});
  const [dlgOpen, setDlgOpen] = useState(false);
  const [editing, setEditing] = useState<CameraRow | null>(null);
  const selectedId = selected?.id;

  const pick = useCallback((camera: CameraRow, profs = profiles) => {
    setSelected(camera);
    setSettings(profs.find((p) => p.camera_id === camera.id && p.mode === profileMode)?.settings ?? {});
  }, [profileMode, profiles]);

  const load = useCallback(async () => {
    const [cams, profs] = await Promise.all([SkyApi.cameras(), SkyApi.cameraProfiles()]);
    setCameras(cams);
    setProfiles(profs);
    const first = selectedId ? cams.find((c) => c.id === selectedId) : cams[0];
    if (first) {
      setSelected(first);
      setSettings(profs.find((p) => p.camera_id === first.id && p.mode === profileMode)?.settings ?? {});
    }
  }, [profileMode, selectedId]);

  useEffect(() => {
    if (!selected) return;
    setSettings(profiles.find((p) => p.camera_id === selected.id && p.mode === profileMode)?.settings ?? {});
  }, [profileMode, profiles, selected]);

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
    const profile = profiles.find((p) => p.camera_id === selected?.id && p.mode === profileMode);
    if (!selected) return;
    try {
      if (profile) {
        await SkyApi.patchProfile(profile.id, settings);
      } else {
        await SkyApi.createProfile({
          camera_id: selected.id,
          name: profileMode === "nighttime" ? "Nighttime" : "Daytime",
          mode: profileMode,
          settings,
        });
      }
      toast.success(`${profileMode === "nighttime" ? "Night" : "Day"} profile saved`);
      await load();
    } catch (e: any) {
      toast.error(e.message ?? "Settings save failed");
    }
  }

  async function runTest() {
    if (!selected) return;
    try {
      await SkyApi.testShot({ camera_id: selected.id, exposure_ms: Number(settings.manual_exposure_ms ?? 1000), gain: Number(settings.gain ?? 1), mode: "manual", settings });
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

            <div className="inline-flex w-fit rounded-md border border-border bg-muted/30 p-1">
              <button type="button" onClick={() => setProfileMode("nighttime")} className={`px-3 py-1.5 text-sm rounded-sm ${profileMode === "nighttime" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}>Night</button>
              <button type="button" onClick={() => setProfileMode("daytime")} className={`px-3 py-1.5 text-sm rounded-sm ${profileMode === "daytime" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}>Day</button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <ToggleRow label="Capture" description="Daemon may take images in this mode." help="Allows the scheduler to capture frames while this day or night profile is active." checked={Boolean(settings.capture_enabled)} onChange={(v) => setSettings({ ...settings, capture_enabled: v })} />
              <ToggleRow label="Save frames" description="Off keeps latest updated without growing the gallery." help="Enable to keep every scheduled frame in the gallery. Disable for latest-only daytime operation." checked={settings.save_enabled !== false} onChange={(v) => setSettings({ ...settings, save_enabled: v })} />
              <Field label="Interval (seconds)" help="Time between scheduled captures while this profile is active." type="number" min={1} value={String(settings.interval_seconds ?? (profileMode === "nighttime" ? 30 : 300))} onChange={(v) => setSettings({ ...settings, interval_seconds: Math.max(1, Number(v) || 1) })} />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <ToggleRow label="Auto exposure" description="Let the camera choose daytime exposure." help="Uses the camera adapter's auto exposure mode where supported. Manual exposure is ignored while enabled." checked={Boolean(settings.auto_exposure)} onChange={(v) => setSettings({ ...settings, auto_exposure: v })} />
              <ToggleRow label="Auto gain" description="Let the camera choose analog gain." help="Lets the camera adapter adjust gain. Manual gain is ignored while enabled." checked={Boolean(settings.auto_gain)} onChange={(v) => setSettings({ ...settings, auto_gain: v })} />
              <Field label="Manual exposure (ms)" help="Fixed exposure time in milliseconds for this profile. Use very small values for bright daytime scenes." type="number" min={0.001} step={0.001} disabled={Boolean(settings.auto_exposure)} value={String(settings.manual_exposure_ms ?? 1000)} onChange={(v) => setSettings({ ...settings, manual_exposure_ms: Number(v) })} />
              <Field label="Gain" help="Fixed camera gain when auto gain is disabled. Higher gain brightens the image but increases noise." type="number" disabled={Boolean(settings.auto_gain)} value={String(settings.gain ?? 1)} onChange={(v) => setSettings({ ...settings, gain: Number(v) })} />
              <Field label="Max auto exposure (ms)" help="Upper exposure limit for auto exposure so the camera does not choose exposures longer than this profile should allow." type="number" value={String(settings.max_auto_exposure_ms ?? 30000)} onChange={(v) => setSettings({ ...settings, max_auto_exposure_ms: Number(v) })} />
              <Field label="Mean target" help="Target normalized image brightness for exposure automation. Lower values produce darker frames." type="number" step="0.01" value={String(settings.mean_target ?? 0.28)} onChange={(v) => setSettings({ ...settings, mean_target: Number(v) })} />
              <Field label="Ramp min exposure (ms)" help="Minimum scheduled exposure used when exposure ramping starts or recovers from an overexposed frame." type="number" min={0.001} step={0.001} value={String(settings.ramp_min_exposure_ms ?? 1)} onChange={(v) => setSettings({ ...settings, ramp_min_exposure_ms: Number(v) })} />
              <Field label="Ramp max exposure (ms)" help="Maximum scheduled exposure that brightness feedback may choose for this profile." type="number" min={0.001} step={1} value={String(settings.ramp_max_exposure_ms ?? settings.max_auto_exposure_ms ?? settings.manual_exposure_ms ?? 30000)} onChange={(v) => setSettings({ ...settings, ramp_max_exposure_ms: Number(v) })} />
              <Field label="Ramp min gain" help="Minimum gain used by scheduled exposure ramping." type="number" min={0} step="0.1" value={String(settings.ramp_min_gain ?? 1)} onChange={(v) => setSettings({ ...settings, ramp_min_gain: Number(v) })} />
              <Field label="Ramp max gain" help="Maximum gain that brightness feedback may choose after exposure reaches its cap." type="number" min={0} step="0.1" value={String(settings.ramp_max_gain ?? settings.max_auto_gain ?? settings.gain ?? 1)} onChange={(v) => setSettings({ ...settings, ramp_max_gain: Number(v) })} />
              <Field label="Saturation limit (%)" help="If more pixels than this are clipped white, scheduled ramping reduces exposure aggressively." type="number" min={0} max={100} step="0.1" value={String(settings.max_saturated_pixels_percent ?? 2)} onChange={(v) => setSettings({ ...settings, max_saturated_pixels_percent: Number(v) })} />
              <Field label="Ramp state age (seconds)" help="How long the last brightness recommendation remains valid. Older state resets to the ramp start exposure." type="number" min={1} value={String(settings.ramp_state_max_age_seconds ?? 1800)} onChange={(v) => setSettings({ ...settings, ramp_state_max_age_seconds: Number(v) })} />
              <ToggleRow label="Auto white balance" description="Use rpicam AWB instead of fixed red/blue gains." help="Lets the camera adapter choose color balance. Disable it to use fixed red and blue balance values." checked={settings.auto_white_balance !== false} onChange={(v) => setSettings({ ...settings, auto_white_balance: v })} />
              <div className="space-y-2">
                <ConfigLabel label="AWB mode" help="White-balance preset passed to the camera adapter when auto white balance is enabled." />
                <Select value={settings.awb ?? "auto"} onValueChange={(v) => setSettings({ ...settings, awb: v })} disabled={settings.auto_white_balance === false}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {["auto", "daylight", "cloudy", "indoor", "fluorescent", "incandescent", "tungsten", "custom"].map((mode) => <SelectItem key={mode} value={mode}>{mode}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <Field label="Red balance" help="Manual red-channel multiplier used only when auto white balance is disabled." type="number" step="0.1" disabled={settings.auto_white_balance !== false} value={String(settings.red_balance ?? 1)} onChange={(v) => setSettings({ ...settings, red_balance: Number(v) })} />
              <Field label="Blue balance" help="Manual blue-channel multiplier used only when auto white balance is disabled." type="number" step="0.1" disabled={settings.auto_white_balance !== false} value={String(settings.blue_balance ?? 1)} onChange={(v) => setSettings({ ...settings, blue_balance: Number(v) })} />
            </div>

            {profileMode === "nighttime" && (
              <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                <ToggleRow label="Keogram" description="Queue after night ends." help="Generates a keogram from the saved night frames after the capture window ends." checked={Boolean(settings.end_of_night_keogram)} onChange={(v) => setSettings({ ...settings, end_of_night_keogram: v })} />
                <ToggleRow label="Startrail" description="Queue after night ends." help="Generates a startrail image from the saved night frames after the capture window ends." checked={Boolean(settings.end_of_night_startrail)} onChange={(v) => setSettings({ ...settings, end_of_night_startrail: v })} />
                <ToggleRow label="Timelapse" description="Queue after night ends." help="Queues a full-night video timelapse after the capture window ends." checked={Boolean(settings.end_of_night_timelapse)} onChange={(v) => setSettings({ ...settings, end_of_night_timelapse: v })} />
                <ToggleRow label="Mini timelapse" description="Queue after night ends." help="Queues a smaller preview timelapse after the capture window ends." checked={Boolean(settings.end_of_night_mini_timelapse)} onChange={(v) => setSettings({ ...settings, end_of_night_mini_timelapse: v })} />
              </div>
            )}

            <div className="flex justify-end">
              <Button onClick={saveSettings} className="bg-gradient-primary text-primary-foreground">Save {profileMode === "nighttime" ? "night" : "day"} profile</Button>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}

function Field({ label, help, value, onChange, ...rest }: { label: string; help?: React.ReactNode; value: string; onChange: (v: string) => void } & React.InputHTMLAttributes<HTMLInputElement>) {
  return <div className="space-y-2"><ConfigLabel label={label} help={help} /><Input value={value} onChange={(e) => onChange(e.target.value)} {...rest} /></div>;
}

function ToggleRow({ label, description, help, checked, onChange }: { label: string; description: string; help?: React.ReactNode; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-border bg-muted/20 p-3">
      <div className="min-w-0">
        <ConfigLabel label={label} help={help} />
        <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
      </div>
      <Switch checked={checked} onCheckedChange={onChange} />
    </div>
  );
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
        <Field label="Name" help="Human-readable camera name shown in the UI, jobs, and metadata." value={name} onChange={setName} placeholder="Roof All-Sky" />
        <Field label="Model" help="Optional model identifier, such as IMX477, IMX290, or ASI224MC." value={model} onChange={setModel} placeholder="IMX477 / IMX708 / ASI224MC" />
        <div className="space-y-2">
          <ConfigLabel label="Adapter" help="Hardware adapter used by the capture daemon. Pick the adapter that matches how the camera is controlled." />
          <Select value={adapter} onValueChange={(v) => setAdapter(v as AdapterType)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>{ADAPTERS.map((a) => <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>)}</SelectContent>
          </Select>
          {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
        </div>
        <div className="flex items-center gap-2 text-sm">
          <input id="primary-camera" type="checkbox" checked={primary} onChange={(e) => setPrimary(e.target.checked)} />
          <Label htmlFor="primary-camera">Primary camera</Label>
          <ConfigHelp label="Primary camera">The primary camera is used by default for dashboard status, scheduled capture, and one-click test shots.</ConfigHelp>
        </div>
      </div>
      <DialogFooter>
        <Button onClick={() => onSave({ name, model: model || null, adapter, is_primary: primary })} className="bg-gradient-primary text-primary-foreground">{editing ? "Save" : "Create"}</Button>
      </DialogFooter>
    </DialogContent>
  );
}
