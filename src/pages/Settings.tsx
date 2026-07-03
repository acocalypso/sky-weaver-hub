import { useCallback, useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { ConfigLabel } from "@/components/ConfigHelp";
import { StatusBadge } from "@/components/StatusBadge";
import { SkyApi, type CameraRow, type DarkFrameRow, type SystemTime, type WifiNetwork, type WifiStatus } from "@/lib/api";
import { Settings as SettingsIcon, MapPin, HardDrive, Shield, Trash2, Camera, Plus, CheckCircle2, RefreshCw, SlidersHorizontal, Clock, Wifi } from "lucide-react";
import { toast } from "sonner";

export default function SettingsPage() {
  const [values, setValues] = useState<Record<string, any> | null>(null);
  const [cameras, setCameras] = useState<CameraRow[]>([]);
  const [darkFrames, setDarkFrames] = useState<DarkFrameRow[]>([]);
  const [darkForm, setDarkForm] = useState({ camera_id: "", label: "", exposure_ms: 1000, gain: 1, width: 1280, height: 960, count: 5 });
  const [cleaningRetention, setCleaningRetention] = useState(false);
  const [capturingDark, setCapturingDark] = useState(false);
  const [activatingDarkId, setActivatingDarkId] = useState<string | null>(null);
  const [systemTime, setSystemTime] = useState<SystemTime | null>(null);
  const [wifiStatus, setWifiStatus] = useState<WifiStatus | null>(null);
  const [wifiNetworks, setWifiNetworks] = useState<WifiNetwork[]>([]);
  const [wifiForm, setWifiForm] = useState({ ssid: "", password: "", hidden: false });
  const [syncingTime, setSyncingTime] = useState(false);
  const [scanningWifi, setScanningWifi] = useState(false);
  const [connectingWifi, setConnectingWifi] = useState(false);

  const load = useCallback(async () => {
    try {
      const [nextValues, nextCameras, nextDarkFrames, nextTime, nextWifi] = await Promise.all([SkyApi.settings(), SkyApi.cameras(), SkyApi.darkFrames(), SkyApi.systemTime(), SkyApi.wifiStatus()]);
      setValues(nextValues);
      setCameras(nextCameras);
      setDarkFrames(nextDarkFrames);
      setSystemTime(nextTime);
      setWifiStatus(nextWifi);
      const primary = nextCameras.find((camera) => camera.is_primary) ?? nextCameras[0];
      if (primary && !darkForm.camera_id) setDarkForm((current) => ({ ...current, camera_id: primary.id }));
    } catch (e: any) {
      toast.error(e.message ?? "Settings load failed");
    }
  }, [darkForm.camera_id]);

  useEffect(() => {
    document.title = "Settings - Sky Weaver Hub";
    load();
  }, [load]);

  if (!values) return <p className="text-sm text-muted-foreground">Loading...</p>;
  const observatory = values.observatory ?? {};
  const storage = values.storage ?? {};
  const publicPage = values.public_page ?? {};
  const processing = values.processing ?? {};
  const darkFrameSettings = values.dark_frames ?? {};
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

  async function runRetentionCleanup() {
    if (!values || cleaningRetention) return;
    setCleaningRetention(true);
    try {
      const days = Math.max(0, Number(values.storage?.retention_days ?? 30));
      const [imageResult, productResult] = await Promise.all([SkyApi.runImageRetention(days), SkyApi.runProductRetention(days)]);
      const deletedFiles = imageResult.deleted_files.length + productResult.deleted_files.length;
      toast.success(`Deleted ${imageResult.deleted_images} image${imageResult.deleted_images === 1 ? "" : "s"}, ${productResult.deleted_products} product${productResult.deleted_products === 1 ? "" : "s"}, and ${deletedFiles} file${deletedFiles === 1 ? "" : "s"}`);
    } catch (e: any) {
      toast.error(e.message ?? "Retention cleanup failed");
    } finally {
      setCleaningRetention(false);
    }
  }

  async function captureDarkFrameSet() {
    if (capturingDark) return;
    setCapturingDark(true);
    try {
      const job = await SkyApi.captureDarkFrameSet({
        camera_id: darkForm.camera_id || null,
        label: darkForm.label || null,
        exposure_ms: Number(darkForm.exposure_ms),
        gain: Number(darkForm.gain),
        width: Number(darkForm.width),
        height: Number(darkForm.height),
        format: "png",
        count: Number(darkForm.count),
        set_active: true,
      });
      toast.success(`Dark-frame capture queued: ${job.id}`);
    } catch (e: any) {
      toast.error(e.message ?? "Dark-frame capture failed");
    } finally {
      setCapturingDark(false);
    }
  }

  async function activateDarkFrame(frame: DarkFrameRow) {
    setActivatingDarkId(frame.id);
    try {
      const result = await SkyApi.activateDarkFrame(frame.id);
      updateGroup("dark_frames", result.settings);
      await load();
      toast.success("Dark-frame set selected");
    } catch (e: any) {
      toast.error(e.message ?? "Dark-frame selection failed");
    } finally {
      setActivatingDarkId(null);
    }
  }

  async function deleteDarkFrame(frame: DarkFrameRow) {
    try {
      const result = await SkyApi.deleteDarkFrame(frame.id);
      setDarkFrames(darkFrames.filter((item) => item.id !== frame.id));
      toast.success(`Deleted dark-frame set and ${result.deleted_files.length} file${result.deleted_files.length === 1 ? "" : "s"}`);
    } catch (e: any) {
      toast.error(e.message ?? "Delete failed");
    }
  }

  async function syncTimeFromBrowser() {
    setSyncingTime(true);
    try {
      const result = await SkyApi.syncSystemTime({
        browser_epoch_ms: Date.now(),
        browser_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      });
      toast.success(`Pi time synced; previous drift ${result.previous_drift_seconds ?? 0}s`);
      setSystemTime(await SkyApi.systemTime());
    } catch (e: any) {
      toast.error(e.message ?? "Time sync failed");
    } finally {
      setSyncingTime(false);
    }
  }

  async function scanWifiNetworks() {
    setScanningWifi(true);
    try {
      const result = await SkyApi.scanWifi();
      setWifiNetworks(result.networks);
      if (!wifiForm.ssid && result.networks[0]?.ssid) setWifiForm((current) => ({ ...current, ssid: result.networks[0].ssid }));
      toast.message(result.message);
    } catch (e: any) {
      toast.error(e.message ?? "Wi-Fi scan failed");
    } finally {
      setScanningWifi(false);
    }
  }

  async function connectWifiNetwork() {
    setConnectingWifi(true);
    try {
      const result = await SkyApi.connectWifi({ ssid: wifiForm.ssid, password: wifiForm.password || null, hidden: wifiForm.hidden });
      if (result.status === "connected") toast.success(result.message);
      else toast.error(result.message);
      setWifiStatus(await SkyApi.wifiStatus());
    } catch (e: any) {
      toast.error(e.message ?? "Wi-Fi connect failed");
    } finally {
      setConnectingWifi(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-widest text-muted-foreground">Configuration</p>
        <h1 className="text-3xl font-semibold tracking-tight flex items-center gap-3"><SettingsIcon className="h-7 w-7 text-primary" /> Settings</h1>
      </div>

      <Section icon={<MapPin className="h-4 w-4 text-primary" />} title="Location">
        <Field label="Observatory name" help="Displayed in the dashboard, public page, overlays, and exported metadata." value={observatory.name ?? ""} onChange={(v) => updateGroup("observatory", { name: v })} />
        <Field label="Latitude" help="Decimal latitude used for sun altitude, twilight, and scheduler calculations. North is positive." type="number" step="0.0001" value={String(observatory.latitude ?? 0)} onChange={(v) => updateGroup("observatory", { latitude: Number(v) })} />
        <Field label="Longitude" help="Decimal longitude used for sun altitude, twilight, and scheduler calculations. East is positive." type="number" step="0.0001" value={String(observatory.longitude ?? 0)} onChange={(v) => updateGroup("observatory", { longitude: Number(v) })} />
        <Field label="Timezone" help="IANA timezone name used to present local times and calculate daily schedule windows." value={observatory.timezone ?? "UTC"} onChange={(v) => updateGroup("observatory", { timezone: v })} />
      </Section>

      <Section icon={<Wifi className="h-4 w-4 text-primary" />} title="Pi Device Access">
        <div className="space-y-3 rounded-md border border-border bg-muted/20 p-3">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-sm font-medium flex items-center gap-2"><Clock className="h-4 w-4 text-primary" /> Browser time sync</p>
              <p className="mt-1 text-xs text-muted-foreground font-mono-data">{systemTime?.server_time ? new Date(systemTime.server_time).toLocaleString() : "Pi time unavailable"}</p>
            </div>
            <Button type="button" variant="outline" onClick={syncTimeFromBrowser} disabled={syncingTime}>
              <Clock className="h-4 w-4 mr-2" />{syncingTime ? "Syncing..." : "Sync now"}
            </Button>
          </div>
        </div>
        <div className="space-y-3 rounded-md border border-border bg-muted/20 p-3">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-sm font-medium flex items-center gap-2"><Wifi className="h-4 w-4 text-primary" /> Wi-Fi</p>
              <p className="mt-1 text-xs text-muted-foreground">{wifiStatus?.available ? (wifiStatus.active[0]?.ssid ? `Connected to ${wifiStatus.active[0].ssid}` : "No active Wi-Fi connection reported") : (wifiStatus?.message ?? "Wi-Fi status unavailable")}</p>
            </div>
            <Button type="button" variant="outline" onClick={scanWifiNetworks} disabled={scanningWifi}>
              <RefreshCw className="h-4 w-4 mr-2" />{scanningWifi ? "Scanning..." : "Scan"}
            </Button>
          </div>
          <div className="grid grid-cols-1 gap-3">
            <div className="space-y-2">
              <ConfigLabel label="Network" help="Wi-Fi network found by the Pi scan. Select the SSID to connect the Pi to a different network." />
              <select className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={wifiForm.ssid} onChange={(event) => setWifiForm({ ...wifiForm, ssid: event.target.value })}>
                <option value="">Select network</option>
                {wifiNetworks.map((network) => <option key={`${network.ssid}-${network.security}-${network.channel}`} value={network.ssid}>{network.ssid} {network.signal == null ? "" : `(${network.signal}%)`} {network.security || "open"}</option>)}
              </select>
            </div>
            <Field label="Password" help="Password for the selected Wi-Fi network. Leave empty only for open networks." type="password" value={wifiForm.password} onChange={(v) => setWifiForm({ ...wifiForm, password: v })} placeholder="Open network: leave empty" />
            <Toggle label="Hidden SSID" hint="Use hidden network connection mode for the selected SSID." help="Enable this when the network does not broadcast its SSID. The Pi will attempt a hidden-network connection." value={wifiForm.hidden} onChange={(v) => setWifiForm({ ...wifiForm, hidden: v })} />
            <Button type="button" onClick={connectWifiNetwork} disabled={connectingWifi || !wifiForm.ssid}>
              <Wifi className="h-4 w-4 mr-2" />{connectingWifi ? "Connecting..." : "Connect"}
            </Button>
          </div>
        </div>
      </Section>

      <Section icon={<HardDrive className="h-4 w-4 text-primary" />} title="Storage and retention">
        <Field label="Image storage path" help="Filesystem path where captured images and thumbnails are stored. Keep it on persistent local storage." value={storage.images ?? "./data/images"} onChange={(v) => updateGroup("storage", { images: v })} />
        <Field label="Video storage path" help="Filesystem path where generated timelapses and night products are stored." value={storage.videos ?? "./data/videos"} onChange={(v) => updateGroup("storage", { videos: v })} />
        <Field label="Retention days" help="How many days of images and generated products to keep when retention cleanup runs." type="number" value={String(storage.retention_days ?? 30)} onChange={(v) => updateGroup("storage", { retention_days: Number(v) })} />
        <Field label="Minimum free GB" help="Target free disk space threshold. Keep enough headroom for overnight captures and generated videos." type="number" value={String(storage.min_free_gb ?? 2)} onChange={(v) => updateGroup("storage", { min_free_gb: Number(v) })} />
        <div className="flex items-end">
          <Button type="button" variant="outline" className="w-full" onClick={runRetentionCleanup} disabled={cleaningRetention}>
            <Trash2 className="h-4 w-4 mr-2" />{cleaningRetention ? "Cleaning..." : "Run retention cleanup"}
          </Button>
        </div>
      </Section>

      <Section icon={<Shield className="h-4 w-4 text-primary" />} title="Public and API">
        <Toggle label="Public page enabled" hint="Expose /public without admin controls." help="When enabled, unauthenticated visitors can view the public sky page and public latest/product APIs." value={Boolean(publicPage.enabled)} onChange={(v) => updateGroup("public_page", { enabled: v })} />
        <Toggle label="Iframe mode enabled" hint="Allow an embeddable read-only public sky view." help="Allows the public view to be embedded in another page. Keep disabled if you do not need iframe embedding." value={Boolean(publicPage.iframe_enabled)} onChange={(v) => updateGroup("public_page", { iframe_enabled: v })} />
        <Field label="Public product days" help="Limits how many recent days of keograms, startrails, and timelapses are visible on the public page." type="number" min={1} max={3650} value={String(publicPage.product_days ?? 7)} onChange={(v) => updateGroup("public_page", { product_days: Number(v) })} />
        <Field label="CORS origins" help="Comma-separated browser origins allowed to call the API. Leave empty unless a separate local client needs API access." value={(security.cors_origins ?? []).join(",")} onChange={(v) => updateGroup("security", { cors_origins: v.split(",").map((x) => x.trim()).filter(Boolean) })} />
        <Toggle label="First setup required" hint="Installer should force a password change before unattended use." help="Keeps the first-run setup flow active until the admin password and essential settings are confirmed." value={Boolean(security.first_setup_required)} onChange={(v) => updateGroup("security", { first_setup_required: v })} />
      </Section>

      <Section icon={<SlidersHorizontal className="h-4 w-4 text-primary" />} title="Processing Quality">
        <Field label="Minimum brightness" help="Frames darker than this normalized mean brightness can be flagged as bad for downstream products." type="number" min={0} max={1} step="0.001" value={String(processing.bad_image_min_brightness ?? 0.01)} onChange={(v) => updateGroup("processing", { bad_image_min_brightness: Number(v) })} />
        <Field label="Maximum brightness" help="Frames brighter than this normalized mean brightness can be flagged as overexposed." type="number" min={0} max={1} step="0.001" value={String(processing.bad_image_max_brightness ?? 0.98)} onChange={(v) => updateGroup("processing", { bad_image_max_brightness: Number(v) })} />
        <Field label="Maximum cloud score" help="Optional cloud-score threshold for rejecting frames from products. Leave empty to disable this filter." type="number" min={0} max={1} step="0.001" placeholder="Off" value={processing.bad_image_max_cloud_score == null ? "" : String(processing.bad_image_max_cloud_score)} onChange={(v) => updateGroup("processing", { bad_image_max_cloud_score: v === "" ? null : Number(v) })} />
      </Section>

      <Section icon={<Camera className="h-4 w-4 text-primary" />} title="Dark Frame Calibration">
        <Toggle label="Enable calibration" hint="Apply matching master dark frames to new captures before processing." help="When enabled, Sky Weaver subtracts a matching master dark frame from new captures before saving and processing." value={Boolean(darkFrameSettings.enabled)} onChange={(v) => updateGroup("dark_frames", { enabled: v })} />
        <div className="space-y-2">
          <ConfigLabel label="Selection mode" help="Auto chooses the best dark frame by camera and capture settings. Manual uses the active selected set." />
          <select className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={darkFrameSettings.selection_mode ?? "auto"} onChange={(event) => updateGroup("dark_frames", { selection_mode: event.target.value })}>
            <option value="auto">Auto match by camera and settings</option>
            <option value="manual">Use selected active set</option>
          </select>
        </div>
        <div className="space-y-2">
          <ConfigLabel label="Camera" help="Camera that the new dark-frame set belongs to. Dark frames are never shared across cameras." />
          <select className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={darkForm.camera_id} onChange={(event) => setDarkForm({ ...darkForm, camera_id: event.target.value })}>
            {cameras.map((camera) => <option key={camera.id} value={camera.id}>{camera.name}</option>)}
          </select>
        </div>
        <Field label="Set label" help="Optional human-readable label for this master dark frame, such as the exposure and gain combination." value={darkForm.label} onChange={(v) => setDarkForm({ ...darkForm, label: v })} placeholder="Night 10s gain 4" />
        <Field label="Exposure ms" help="Exposure time used for each dark frame. It should match the sky captures you want to calibrate." type="number" min={1} value={String(darkForm.exposure_ms)} onChange={(v) => setDarkForm({ ...darkForm, exposure_ms: Number(v) })} />
        <Field label="Gain / ISO" help="Gain or ISO used for the dark frame set. It should match the camera profile being calibrated." type="number" min={0} step="0.1" value={String(darkForm.gain)} onChange={(v) => setDarkForm({ ...darkForm, gain: Number(v) })} />
        <Field label="Width" help="Capture width for the dark frames. It must match the sky-frame resolution to be applied." type="number" min={1} value={String(darkForm.width)} onChange={(v) => setDarkForm({ ...darkForm, width: Number(v) })} />
        <Field label="Height" help="Capture height for the dark frames. It must match the sky-frame resolution to be applied." type="number" min={1} value={String(darkForm.height)} onChange={(v) => setDarkForm({ ...darkForm, height: Number(v) })} />
        <Field label="Frame count" help="Number of covered-sensor frames to capture and combine into the master dark. More frames reduce random noise." type="number" min={1} max={100} value={String(darkForm.count)} onChange={(v) => setDarkForm({ ...darkForm, count: Number(v) })} />
        <div className="flex items-end gap-2">
          <Button type="button" className="w-full" onClick={captureDarkFrameSet} disabled={capturingDark || !darkForm.camera_id}>
            <Plus className="h-4 w-4 mr-2" />{capturingDark ? "Queueing..." : "Capture dark set"}
          </Button>
          <Button type="button" variant="outline" onClick={load} aria-label="Refresh dark frames">
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
        <div className="md:col-span-2 space-y-3">
          <h3 className="text-sm font-medium">Available master dark frames</h3>
          {darkFrames.map((frame) => {
            const camera = cameras.find((item) => item.id === frame.camera_id);
            return (
              <div key={frame.id} className="rounded-md border border-border bg-muted/20 p-3 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-medium truncate">{frame.label || "Master dark frame"}</p>
                    <StatusBadge variant={frame.active ? "ok" : "idle"}>{frame.active ? "active" : "stored"}</StatusBadge>
                  </div>
                  <p className="mt-1 font-mono-data text-xs text-muted-foreground truncate">
                    {camera?.name ?? frame.camera_id ?? "unknown camera"} - {frame.exposure_ms ?? "-"} ms - gain {frame.gain ?? "-"} - {frame.width ?? "-"}x{frame.height ?? "-"} - {frame.frame_count ?? 1} frames
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button variant="outline" size="sm" onClick={() => activateDarkFrame(frame)} disabled={frame.active || activatingDarkId === frame.id}>
                    <CheckCircle2 className="h-4 w-4 mr-2" />Select
                  </Button>
                  <Button variant="destructive" size="sm" onClick={() => deleteDarkFrame(frame)}>
                    <Trash2 className="h-4 w-4 mr-2" />Delete
                  </Button>
                </div>
              </div>
            );
          })}
          {darkFrames.length === 0 && <p className="text-sm text-muted-foreground">No dark-frame sets captured yet.</p>}
        </div>
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

function Field({ label, help, value, onChange, ...rest }: { label: string; help?: React.ReactNode; value: string; onChange: (v: string) => void } & React.InputHTMLAttributes<HTMLInputElement>) {
  return <div className="space-y-2"><ConfigLabel label={label} help={help} /><Input value={value} onChange={(e) => onChange(e.target.value)} {...rest} /></div>;
}

function Toggle({ label, hint, help, value, onChange }: { label: string; hint: string; help?: React.ReactNode; value: boolean; onChange: (v: boolean) => void }) {
  return <div className="flex items-center justify-between p-3 rounded-md border border-border bg-muted/20"><div><ConfigLabel label={label} help={help} /><p className="text-xs text-muted-foreground mt-0.5">{hint}</p></div><Switch checked={value} onCheckedChange={onChange} /></div>;
}
