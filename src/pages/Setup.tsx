import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Camera, Check, Loader2, MapPin, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { SkyApi, type CameraRow, type SetupStatus } from "@/lib/api";

export default function SetupPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [cameras, setCameras] = useState<CameraRow[]>([]);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [observatoryName, setObservatoryName] = useState("Sky Weaver Observatory");
  const [latitude, setLatitude] = useState("0");
  const [longitude, setLongitude] = useState("0");
  const [timezone, setTimezone] = useState("UTC");
  const [publicPageEnabled, setPublicPageEnabled] = useState(true);
  const [primaryCameraId, setPrimaryCameraId] = useState<string | null>(null);

  useEffect(() => {
    document.title = "First setup - Sky Weaver Hub";
    SkyApi.setupStatus()
      .then((status: SetupStatus) => {
        setCameras(status.cameras ?? []);
        setObservatoryName(status.observatory?.name ?? "Sky Weaver Observatory");
        setLatitude(String(status.observatory?.latitude ?? status.schedule?.latitude ?? 0));
        setLongitude(String(status.observatory?.longitude ?? status.schedule?.longitude ?? 0));
        setTimezone(status.observatory?.timezone ?? status.schedule?.timezone ?? "UTC");
        setPublicPageEnabled(Boolean(status.public_page?.enabled ?? true));
        setPrimaryCameraId(status.cameras?.find((camera) => camera.is_primary)?.id ?? status.cameras?.[0]?.id ?? null);
      })
      .catch((error: Error) => toast.error(error.message))
      .finally(() => setLoading(false));
  }, []);

  async function complete() {
    const lat = Number(latitude);
    const lon = Number(longitude);
    if (!observatoryName.trim()) return toast.error("Observatory name is required");
    if (!Number.isFinite(lat) || lat < -90 || lat > 90) return toast.error("Latitude must be between -90 and 90");
    if (!Number.isFinite(lon) || lon < -180 || lon > 180) return toast.error("Longitude must be between -180 and 180");
    if (!timezone.trim()) return toast.error("Timezone is required");
    if (!password || password.length < 8) return toast.error("Set an admin password with at least 8 characters");
    if (password !== confirm) return toast.error("Passwords do not match");

    setSaving(true);
    try {
      await SkyApi.completeSetup({
        admin_password: password,
        observatory_name: observatoryName.trim(),
        latitude: lat,
        longitude: lon,
        timezone: timezone.trim(),
        public_page_enabled: publicPageEnabled,
        primary_camera_id: primaryCameraId,
      });
      toast.success("Setup completed");
      navigate("/", { replace: true });
    } catch (error: any) {
      toast.error(error.message ?? "Setup failed");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-background text-foreground px-4 py-8">
      <div className="mx-auto max-w-3xl space-y-6">
        <header className="space-y-2">
          <h1 className="text-3xl font-semibold tracking-tight">First setup</h1>
          <p className="text-sm text-muted-foreground">Finish the local observatory configuration before using Sky Weaver Hub.</p>
        </header>

        <Card className="p-5 space-y-4">
          <div className="flex items-center gap-2 text-sm font-medium">
            <ShieldCheck className="h-4 w-4 text-primary" />
            Admin account
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="New admin password" type="password" value={password} onChange={setPassword} />
            <Field label="Confirm password" type="password" value={confirm} onChange={setConfirm} />
          </div>
        </Card>

        <Card className="p-5 space-y-4">
          <div className="flex items-center gap-2 text-sm font-medium">
            <MapPin className="h-4 w-4 text-primary" />
            Observatory
          </div>
          <Field label="Name" value={observatoryName} onChange={setObservatoryName} />
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Latitude" type="number" value={latitude} onChange={setLatitude} />
            <Field label="Longitude" type="number" value={longitude} onChange={setLongitude} />
            <Field label="Timezone" value={timezone} onChange={setTimezone} />
          </div>
        </Card>

        <Card className="p-5 space-y-4">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Camera className="h-4 w-4 text-primary" />
            Camera and public page
          </div>
          <div className="space-y-2">
            <Label htmlFor="primary-camera">Primary camera</Label>
            <select
              id="primary-camera"
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              value={primaryCameraId ?? ""}
              onChange={(event) => setPrimaryCameraId(event.target.value || null)}
            >
              {cameras.map((camera) => (
                <option key={camera.id} value={camera.id}>{camera.name} ({camera.adapter})</option>
              ))}
            </select>
          </div>
          <label className="flex items-center justify-between rounded-md border border-border p-3">
            <span className="text-sm">Public sky page</span>
            <Switch checked={publicPageEnabled} onCheckedChange={setPublicPageEnabled} />
          </label>
        </Card>

        <div className="flex justify-end">
          <Button onClick={complete} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Check className="h-4 w-4 mr-2" />}
            Complete setup
          </Button>
        </div>
      </div>
    </main>
  );
}

function Field({ label, value, onChange, type = "text" }: { label: string; value: string; onChange: (value: string) => void; type?: string }) {
  const id = `setup-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} type={type} value={value} onChange={(event) => onChange(event.target.value)} />
    </div>
  );
}
