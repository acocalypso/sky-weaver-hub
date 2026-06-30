import { useEffect, useMemo, useState } from "react";
import type { InputHTMLAttributes } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { StatusBadge } from "@/components/StatusBadge";
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
            <Field label="Font size" type="number" value={String(overlaySettings.font_size ?? 24)} onChange={(value) => setSetting("font_size", Number(value))} />
            <Field label="Margin" type="number" value={String(overlaySettings.margin ?? 18)} onChange={(value) => setSetting("margin", Number(value))} />
            <Field label="Padding" type="number" value={String(overlaySettings.padding ?? 8)} onChange={(value) => setSetting("padding", Number(value))} />
            <Field label="Text" type="color" value={normalizeColorInput(overlaySettings.text_color ?? "#ffffffff")} onChange={(value) => setSetting("text_color", `${value}ff`)} />
            <Field label="Background" value={overlaySettings.background_color ?? "#00000099"} onChange={(value) => setSetting("background_color", value)} />
          </div>

          <div className="space-y-3">
            {lines.map((line, index) => (
              <div key={index} className="grid grid-cols-1 md:grid-cols-[1fr_180px_auto] gap-3 items-end">
                <Field label={`Line ${index + 1}`} value={line.text ?? ""} onChange={(value) => setLine(index, { text: value })} />
                <div className="space-y-2">
                  <Label>Position</Label>
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
    </div>
  );
}

function Field({ label, value, onChange, ...rest }: { label: string; value: string; onChange: (value: string) => void } & InputHTMLAttributes<HTMLInputElement>) {
  return <div className="space-y-2"><Label>{label}</Label><Input value={value} onChange={(event) => onChange(event.target.value)} {...rest} /></div>;
}

function normalizeColorInput(value: string) {
  const text = value.trim();
  if (/^#[0-9a-fA-F]{6}/.test(text)) return text.slice(0, 7);
  return "#ffffff";
}
