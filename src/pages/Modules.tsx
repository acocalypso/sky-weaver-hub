import { useEffect, useMemo, useState } from "react";
import type { InputHTMLAttributes } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { StatusBadge } from "@/components/StatusBadge";
import { ConfigLabel } from "@/components/ConfigHelp";
import { SkyApi, type ModuleFlowRow, type ModuleRow } from "@/lib/api";
import { Play, Plus, Puzzle, Save, Trash2 } from "lucide-react";
import { toast } from "sonner";

const POSITIONS = ["top_left", "top_center", "top_right", "center_left", "center", "center_right", "bottom_left", "bottom_center", "bottom_right"];

export default function Modules() {
  const [modules, setModules] = useState<ModuleRow[]>([]);
  const [flows, setFlows] = useState<ModuleFlowRow[]>([]);
  const [overlaySettings, setOverlaySettings] = useState<Record<string, any>>({});
  const [overlayEnabled, setOverlayEnabled] = useState(false);
  const [saving, setSaving] = useState(false);
  const [runningFlowId, setRunningFlowId] = useState<string | null>(null);
  const [manifest, setManifest] = useState({ id: "", name: "", version: "0.1.0", author: "" });

  useEffect(() => {
    document.title = "Modules - Sky Weaver Hub";
    load();
  }, []);

  async function load() {
    try {
      const [rows, nextFlows] = await Promise.all([SkyApi.modules(), SkyApi.moduleFlows()]);
      setModules(rows);
      setFlows(nextFlows);
      const overlay = rows.find((row) => row.id === "builtin.overlay");
      if (overlay) {
        setOverlayEnabled(Boolean(overlay.enabled));
        setOverlaySettings(overlay.settings ?? {});
      }
    } catch (e: any) {
      toast.error(e.message ?? "Unable to load modules");
    }
  }

  const overlay = useMemo(() => modules.find((row) => row.id === "builtin.overlay"), [modules]);
  const postCaptureFlow = useMemo(() => flows.find((row) => row.id === "builtin.post_capture"), [flows]);
  const lines = Array.isArray(overlaySettings.lines) ? overlaySettings.lines : [];

  function setSetting(key: string, value: any) {
    setOverlaySettings({ ...overlaySettings, [key]: value });
  }

  function setLine(index: number, patch: Record<string, any>) {
    setOverlaySettings({
      ...overlaySettings,
      lines: lines.map((line, lineIndex) => lineIndex === index ? { ...line, ...patch } : line),
    });
  }

  function addLine() {
    const nextPosition = POSITIONS[Math.min(lines.length, POSITIONS.length - 1)];
    setOverlaySettings({
      ...overlaySettings,
      lines: [...lines, { text: "{captured_time}", position: nextPosition }],
    });
  }

  function removeLine(index: number) {
    setOverlaySettings({
      ...overlaySettings,
      lines: lines.filter((_line, lineIndex) => lineIndex !== index),
    });
  }

  async function saveOverlay() {
    if (!overlay) return;
    setSaving(true);
    try {
      const updated = await SkyApi.patchModule(overlay.id, { enabled: overlayEnabled, settings: overlaySettings });
      setModules(modules.map((row) => row.id === updated.id ? updated : row));
      setOverlayEnabled(updated.enabled);
      setOverlaySettings(updated.settings ?? {});
      toast.success("Overlay module saved");
    } catch (e: any) {
      toast.error(e.message ?? "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function setFlowEnabled(flow: ModuleFlowRow, enabled: boolean) {
    try {
      const updated = await SkyApi.patchModuleFlow(flow.id, { enabled });
      setFlows(flows.map((row) => row.id === updated.id ? updated : row));
      toast.success("Module flow saved");
    } catch (e: any) {
      toast.error(e.message ?? "Flow save failed");
    }
  }

  async function runFlow(flow: ModuleFlowRow) {
    setRunningFlowId(flow.id);
    try {
      const result = await SkyApi.runModuleFlow(flow.id);
      const ready = result.modules.filter((module) => module.status === "ready").length;
      toast.success(`${flow.name}: ${ready} ready`);
    } catch (e: any) {
      toast.error(e.message ?? "Flow run failed");
    } finally {
      setRunningFlowId(null);
    }
  }

  async function registerManifest() {
    try {
      const registered = await SkyApi.registerModule({
        id: manifest.id,
        name: manifest.name,
        version: manifest.version,
        author: manifest.author,
        capabilities: ["post_capture"],
        settings_schema: { type: "object" },
        settings: {},
      });
      setModules([registered, ...modules.filter((row) => row.id !== registered.id)]);
      setManifest({ id: "", name: "", version: "0.1.0", author: "" });
      toast.success("Module manifest registered");
    } catch (e: any) {
      toast.error(e.message ?? "Manifest registration failed");
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-widest text-muted-foreground">Processing</p>
        <h1 className="text-3xl font-semibold tracking-tight flex items-center gap-3"><Puzzle className="h-7 w-7 text-primary" /> Modules</h1>
      </div>

      {overlay && (
        <Card className="telemetry-card space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold">{overlay.name}</h2>
              <p className="text-xs text-muted-foreground">{overlay.description}</p>
            </div>
            <div className="flex items-center gap-3">
              <StatusBadge variant={overlay.trusted ? "ok" : "warn"}>{overlay.trusted ? "trusted" : "untrusted"}</StatusBadge>
              <Switch checked={overlayEnabled} onCheckedChange={setOverlayEnabled} />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
            <Field label="Font size" help="Overlay text size in pixels for rendered capture annotations." type="number" value={String(overlaySettings.font_size ?? 24)} onChange={(value) => setSetting("font_size", Number(value))} />
            <Field label="Margin" help="Distance in pixels between overlay text blocks and the image edge." type="number" value={String(overlaySettings.margin ?? 18)} onChange={(value) => setSetting("margin", Number(value))} />
            <Field label="Padding" help="Padding in pixels inside each overlay text background box." type="number" value={String(overlaySettings.padding ?? 8)} onChange={(value) => setSetting("padding", Number(value))} />
            <Field label="Text" help="Text color used for overlay annotations." type="color" value={normalizeColorInput(overlaySettings.text_color ?? "#ffffffff")} onChange={(value) => setSetting("text_color", `${value}ff`)} />
            <Field label="Background" help="Overlay background color. Supports hex values with optional alpha, such as #00000099." value={overlaySettings.background_color ?? "#00000099"} onChange={(value) => setSetting("background_color", value)} />
          </div>

          <div className="space-y-3">
            {lines.map((line, index) => (
              <div key={index} className="grid grid-cols-1 md:grid-cols-[1fr_180px_auto] gap-3 items-end">
                <Field label={`Line ${index + 1}`} help="Overlay text template for this line. Variables such as {observatory_name} and {captured_time} are resolved during processing." value={line.text ?? ""} onChange={(value) => setLine(index, { text: value })} />
                <div className="space-y-2">
                  <ConfigLabel label="Position" help="Image anchor where this overlay line is rendered." />
                  <select className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm" value={line.position ?? "bottom_left"} onChange={(event) => setLine(index, { position: event.target.value })}>
                    {POSITIONS.map((position) => <option key={position} value={position}>{position.replace("_", " ")}</option>)}
                  </select>
                </div>
                <Button type="button" variant="outline" size="icon" onClick={() => removeLine(index)} aria-label={`Remove line ${index + 1}`}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>

          <div className="flex flex-wrap justify-between gap-3">
            <Button type="button" variant="outline" onClick={addLine} disabled={lines.length >= 8}>
              <Plus className="h-4 w-4 mr-2" />Add line
            </Button>
            <Button onClick={saveOverlay} disabled={saving}><Save className="h-4 w-4 mr-2" />{saving ? "Saving..." : "Save overlay"}</Button>
          </div>
        </Card>
      )}

      {postCaptureFlow && (
        <Card className="telemetry-card space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold">{postCaptureFlow.name}</h2>
              <p className="text-xs text-muted-foreground">Trigger: {postCaptureFlow.trigger.replace("_", " ")}</p>
            </div>
            <div className="flex items-center gap-3">
              <StatusBadge variant={postCaptureFlow.enabled ? "active" : "idle"}>{postCaptureFlow.enabled ? "enabled" : "disabled"}</StatusBadge>
              <Switch checked={postCaptureFlow.enabled} onCheckedChange={(checked) => setFlowEnabled(postCaptureFlow, checked)} />
              <Button variant="outline" size="sm" onClick={() => runFlow(postCaptureFlow)} disabled={runningFlowId === postCaptureFlow.id}>
                <Play className="h-4 w-4 mr-2" />{runningFlowId === postCaptureFlow.id ? "Running..." : "Validate"}
              </Button>
            </div>
          </div>
          <div className="space-y-2">
            {postCaptureFlow.module_order.map((moduleId, index) => {
              const module = modules.find((row) => row.id === moduleId);
              return (
                <div key={moduleId} className="flex items-center justify-between border border-border rounded-md p-3">
                  <div>
                    <p className="font-medium">{index + 1}. {module?.name ?? moduleId}</p>
                    <p className="text-xs text-muted-foreground">{moduleId}</p>
                  </div>
                  <StatusBadge variant={module?.enabled ? "active" : "idle"}>{module?.enabled ? "ready" : "skipped"}</StatusBadge>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      <Card className="telemetry-card space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Installed modules</h2>
        {modules.map((module) => (
          <div key={module.id} className="flex items-center justify-between border border-border rounded-md p-3">
            <div>
              <p className="font-medium">{module.name}</p>
              <p className="text-xs text-muted-foreground">{module.id}</p>
            </div>
            <StatusBadge variant={module.enabled ? "active" : "idle"}>{module.enabled ? "enabled" : "disabled"}</StatusBadge>
          </div>
        ))}
      </Card>

      <Card className="telemetry-card space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">External module manifest</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Field label="Module id" help="Stable identifier for the external module manifest, for example external.my-module." value={manifest.id} placeholder="external.my-module" onChange={(value) => setManifest({ ...manifest, id: value })} />
          <Field label="Name" help="Human-readable module name shown in the module list." value={manifest.name} placeholder="My module" onChange={(value) => setManifest({ ...manifest, name: value })} />
          <Field label="Version" help="Module version string used for operator visibility and future compatibility checks." value={manifest.version} onChange={(value) => setManifest({ ...manifest, version: value })} />
          <Field label="Author" help="Optional module author or source label." value={manifest.author} onChange={(value) => setManifest({ ...manifest, author: value })} />
        </div>
        <div className="flex justify-end">
          <Button variant="outline" onClick={registerManifest} disabled={!manifest.id.trim() || !manifest.name.trim()}>
            <Plus className="h-4 w-4 mr-2" />Register manifest
          </Button>
        </div>
      </Card>
    </div>
  );
}

function Field({ label, help, value, onChange, ...rest }: { label: string; help?: React.ReactNode; value: string; onChange: (value: string) => void } & InputHTMLAttributes<HTMLInputElement>) {
  return <div className="space-y-2"><ConfigLabel label={label} help={help} /><Input value={value} onChange={(event) => onChange(event.target.value)} {...rest} /></div>;
}

function normalizeColorInput(value: string) {
  const text = value.trim();
  if (/^#[0-9a-fA-F]{6}/.test(text)) return text.slice(0, 7);
  return "#ffffff";
}
