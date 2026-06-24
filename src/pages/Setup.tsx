import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertCircle, Camera, Check, Loader2, MapPin, Plus, Radar, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { SkyApi, type CameraRow, type DetectedCamera, type SetupStatus } from "@/lib/api";

export default function SetupPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [detecting, setDetecting] = useState(false);
  const [cameras, setCameras] = useState<CameraRow[]>([]);
  const [detected, setDetected] = useState<DetectedCamera[]>([]);
  const [bootstrapPasswordActive, setBootstrapPasswordActive] = useState(false);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [observatoryName, setObservatoryName] = useState("Sky Weaver Observatory");
  const [latitude, setLatitude] = useState("0");
  const [longitude, setLongitude] = useState("0");
  const [timezone, setTimezone] = useState("UTC");
  const [publicPageEnabled, setPublicPageEnabled] = useState(true);
  const [primaryCameraId, setPrimaryCameraId] = useState<string | null>(null);

  const applyStatus = useCallback((status: SetupStatus) => {
    setCameras(status.cameras ?? []);
    setBootstrapPasswordActive(Boolean(status.bootstrap_password_active));
    setObservatoryName(status.observatory?.name ?? "Sky Weaver Observatory");
    setLatitude(String(status.observatory?.latitude ?? status.schedule?.latitude ?? 0));
    setLongitude(String(status.observatory?.longitude ?? status.schedule?.longitude ?? 0));
    setTimezone(status.observatory?.timezone ?? status.schedule?.timezone ?? "UTC");
    setPublicPageEnabled(Boolean(status.public_page?.enabled ?? true));
    setPrimaryCameraId(status.cameras?.find((camera) => camera.is_primary)?.id ?? status.cameras?.[0]?.id ?? null);
  }, []);

  const detectHardware = useCallback(async () => {
    setDetecting(true);
    try {
      setDetected(await SkyApi.detectCameras());
    } catch (error: any) {
      toast.error(error.message ?? "Camera detection failed");
    } finally {
      setDetecting(false);
    }
  }, []);

  const loadSetup = useCallback(async () => {
    setLoading(true);
    try {
      const status = await SkyApi.setupStatus();
      applyStatus(status);
      await detectHardware();
    } catch (error: any) {
      toast.error(error.message ?? "Unable to load setup");
    } finally {
      setLoading(false);
    }
  }, [applyStatus, detectHardware]);

  useEffect(() => {
    document.title = "First setup - Sky Weaver Hub";
    loadSetup();
  }, [loadSetup]);

  async function addDetectedCamera(candidate: DetectedCamera) {
    setSaving(true);
    try {
      const created = await SkyApi.createCamera({
        name: candidate.model?.split(" [")[0]?.replace(/^\d+\s*:\s*/, "") || candidate.name,
        adapter: candidate.backend,
        device_id: candidate.id,
        model: candidate.model ?? candidate.name,
        serial: candidate.serial,
        enabled: true,
        is_primary: true,
      });
      const status = await SkyApi.setupStatus();
      applyStatus(status);
      setPrimaryCameraId(created.id);
      toast.success("Camera added");
    } catch (error: any) {
      toast.error(error.message ?? "Unable to add camera");
    } finally {
      setSaving(false);
    }
  }

  async function complete() {
    const lat = Number(latitude);
    const lon = Number(longitude);
    if (!observatoryName.trim()) return toast.error("Observatory name is required");
    if (!Number.isFinite(lat) || lat < -90 || lat > 90) return toast.error("Latitude must be between -90 and 90");
    if (!Number.isFinite(lon) || lon < -180 || lon > 180) return toast.error("Longitude must be between -180 and 180");
    if (!timezone.trim()) return toast.error("Timezone is required");
    if (passwordIssues.length) return toast.error(passwordIssues[0]);
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

  const hardwareCandidates = detected.filter((camera) => camera.backend !== "mock");
  const configuredHardware = cameras.filter((camera) => camera.adapter !== "mock");
  const unconfiguredHardware = hardwareCandidates.filter((candidate) => !cameras.some((camera) => camera.device_id === candidate.id || camera.adapter === candidate.backend));
  const passwordIssues = getPasswordIssues(password);
  const passwordReady = password.length > 0 && passwordIssues.length === 0 && password === confirm;

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
          {bootstrapPasswordActive && (
            <Alert>
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>Bootstrap password is still active</AlertTitle>
              <AlertDescription>Choose a new admin password before finishing setup.</AlertDescription>
            </Alert>
          )}
          <div className="rounded-md border border-border p-3 text-sm">
            <div className="flex items-center justify-between gap-3">
              <span className="font-medium">Password readiness</span>
              <span className={passwordReady ? "text-emerald-600" : "text-muted-foreground"}>{passwordReady ? "Ready" : "Needs attention"}</span>
            </div>
            <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
              {passwordChecklist(password).map((item) => (
                <li key={item.label} className={item.ok ? "text-emerald-600" : ""}>{item.ok ? "OK" : "-"} {item.label}</li>
              ))}
            </ul>
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
          {configuredHardware.length === 0 && hardwareCandidates.length === 0 && (
            <Alert>
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>No hardware camera detected</AlertTitle>
              <AlertDescription>Setup can continue with the mock camera, but connect a Pi/libcamera camera and use Detect again before unattended capture.</AlertDescription>
            </Alert>
          )}
          {configuredHardware.length === 0 && hardwareCandidates.length > 0 && (
            <Alert>
              <Radar className="h-4 w-4" />
              <AlertTitle>Hardware camera found</AlertTitle>
              <AlertDescription>Select a detected camera below to add it as the primary capture device.</AlertDescription>
            </Alert>
          )}
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <Label>Detected cameras</Label>
              <Button variant="outline" size="sm" onClick={detectHardware} disabled={detecting}>
                {detecting ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Radar className="h-4 w-4 mr-2" />}
                Detect
              </Button>
            </div>
            <div className="space-y-2">
              {hardwareCandidates.map((candidate) => {
                const alreadyConfigured = !unconfiguredHardware.includes(candidate);
                return (
                  <div key={`${candidate.backend}-${candidate.id}`} className="flex items-center justify-between gap-3 rounded-md border border-border p-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{candidate.name}</p>
                      <p className="text-xs text-muted-foreground truncate">{candidate.model ?? candidate.backend}</p>
                    </div>
                    <Button variant="outline" size="sm" onClick={() => addDetectedCamera(candidate)} disabled={saving || alreadyConfigured}>
                      <Plus className="h-4 w-4 mr-2" />
                      {alreadyConfigured ? "Added" : "Add"}
                    </Button>
                  </div>
                );
              })}
              {hardwareCandidates.length === 0 && <p className="text-xs text-muted-foreground">No hardware camera candidates found.</p>}
            </div>
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

function passwordChecklist(password: string) {
  return [
    { label: "At least 12 characters", ok: password.length >= 12 },
    { label: "Different from the bootstrap default", ok: password !== "skyweaver-change-me" },
    { label: "Mix of character types or a long passphrase", ok: passwordCategoryCount(password) >= 3 || password.length >= 20 },
  ];
}

function getPasswordIssues(password: string) {
  if (!password) return ["Set an admin password"];
  return passwordChecklist(password).filter((item) => !item.ok).map((item) => item.label);
}

function passwordCategoryCount(password: string) {
  return [
    /[a-z]/.test(password),
    /[A-Z]/.test(password),
    /\d/.test(password),
    /[^a-zA-Z0-9]/.test(password),
  ].filter(Boolean).length;
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
