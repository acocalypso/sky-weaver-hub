import { useEffect, useState } from "react";
import { format } from "date-fns";
import { Copy, KeyRound, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { SkyApi, type ApiKeyRow } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const SCOPES = ["read:status", "read:images", "read:settings", "write:capture", "write:settings", "write:processing", "admin"];

export default function ApiKeys() {
  const [keys, setKeys] = useState<ApiKeyRow[]>([]);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<string[]>(["read:status", "read:images"]);
  const [newKey, setNewKey] = useState<string | null>(null);

  useEffect(() => {
    document.title = "API Keys - Sky Weaver Hub";
    load();
  }, []);

  async function load() {
    try {
      setKeys(await SkyApi.apiKeys());
    } catch (e) {
      toast.error(errorMessage(e, "Unable to load API keys"));
    }
  }

  async function create() {
    if (!name.trim()) return toast.error("Name is required");
    try {
      const created = await SkyApi.createApiKey({ name: name.trim(), scopes });
      setNewKey(created.key);
      setName("");
      setScopes(["read:status", "read:images"]);
      await load();
    } catch (e) {
      toast.error(errorMessage(e, "Unable to create API key"));
    }
  }

  async function copyKey(value: string) {
    await navigator.clipboard.writeText(value);
    toast.success("Copied API key");
  }

  async function setEnabled(key: ApiKeyRow, enabled: boolean) {
    try {
      await SkyApi.patchApiKey(key.id, { enabled });
      setKeys((cur) => cur.map((item) => item.id === key.id ? { ...item, enabled } : item));
    } catch (e) {
      toast.error(errorMessage(e, "Unable to update API key"));
    }
  }

  async function remove(key: ApiKeyRow) {
    try {
      await SkyApi.deleteApiKey(key.id);
      setKeys((cur) => cur.filter((item) => item.id !== key.id));
      toast.success("API key revoked");
    } catch (e) {
      toast.error(errorMessage(e, "Unable to revoke API key"));
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-widest text-muted-foreground">Security</p>
          <h1 className="text-3xl font-semibold tracking-tight flex items-center gap-3">
            <KeyRound className="h-7 w-7 text-primary" /> API Keys
          </h1>
        </div>
        <Dialog open={open} onOpenChange={(next) => { setOpen(next); if (!next) setNewKey(null); }}>
          <DialogTrigger asChild>
            <Button><Plus className="h-4 w-4 mr-2" /> New key</Button>
          </DialogTrigger>
          <DialogContent className="max-w-xl">
            <DialogHeader><DialogTitle>Create API key</DialogTitle></DialogHeader>
            {newKey ? (
              <div className="space-y-4">
                <div className="rounded-md border border-status-warn/40 bg-status-warn/10 p-3">
                  <p className="text-sm font-medium">Copy this key now. It will only be shown once.</p>
                </div>
                <div className="flex gap-2">
                  <Input readOnly value={newKey} className="font-mono-data" />
                  <Button variant="outline" onClick={() => copyKey(newKey)}><Copy className="h-4 w-4" /></Button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label>Name</Label>
                  <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Mobile app, observatory tablet..." />
                </div>
                <div className="space-y-3">
                  <Label>Scopes</Label>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {SCOPES.map((scope) => (
                      <label key={scope} className="flex items-center gap-2 rounded-md border border-border bg-muted/20 p-2 text-sm font-mono-data">
                        <Checkbox
                          checked={scopes.includes(scope)}
                          onCheckedChange={(checked) => {
                            setScopes((cur) => checked ? [...new Set([...cur, scope])] : cur.filter((item) => item !== scope));
                          }}
                        />
                        {scope}
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            )}
            <DialogFooter>
              {newKey ? <Button onClick={() => setOpen(false)}>Done</Button> : <Button onClick={create}>Create key</Button>}
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <Card className="telemetry-card p-0 overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Prefix</TableHead>
              <TableHead>Scopes</TableHead>
              <TableHead>Created</TableHead>
              <TableHead>Enabled</TableHead>
              <TableHead className="w-[90px] text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {keys.map((key) => (
              <TableRow key={key.id}>
                <TableCell className="font-medium">{key.name}</TableCell>
                <TableCell className="font-mono-data">{key.prefix}</TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1.5">
                    {key.scopes.map((scope) => <Badge key={scope} variant="secondary" className="font-mono-data">{scope}</Badge>)}
                  </div>
                </TableCell>
                <TableCell className="text-muted-foreground">{format(new Date(key.created_at), "yyyy-MM-dd HH:mm")}</TableCell>
                <TableCell><Switch checked={key.enabled} onCheckedChange={(enabled) => setEnabled(key, enabled)} /></TableCell>
                <TableCell className="text-right">
                  <Button variant="ghost" size="icon" onClick={() => remove(key)}><Trash2 className="h-4 w-4 text-status-error" /></Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {keys.length === 0 && <p className="p-6 text-sm text-muted-foreground">No API keys yet.</p>}
      </Card>
    </div>
  );
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}
