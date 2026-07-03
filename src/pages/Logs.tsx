import { useCallback, useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { SkyApi, type LogRow } from "@/lib/api";
import { ScrollText } from "lucide-react";
import { format } from "date-fns";

const LEVEL_COLOR: Record<string, string> = { debug: "text-muted-foreground", info: "text-status-ok", warning: "text-status-warn", error: "text-status-error" };

export default function Logs() {
  const [logs, setLogs] = useState<LogRow[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [level, setLevel] = useState("all");
  const [source, setSource] = useState("");
  const [loadingMore, setLoadingMore] = useState(false);

  const load = useCallback(async (cursor?: string | null) => {
    const params = new URLSearchParams();
    params.set("limit", "100");
    if (level !== "all") params.set("level", level);
    if (source) params.set("source", source);
    if (cursor) params.set("cursor", cursor);
    const query = params.toString() ? `?${params}` : "";
    try {
      const page = await SkyApi.logsPage(query);
      setLogs((current) => cursor ? [...current, ...page.items] : page.items);
      setNextCursor(page.next_cursor);
    } catch { /* keep last log view */ }
  }, [level, source]);

  async function loadMore() {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    try {
      await load(nextCursor);
    } finally {
      setLoadingMore(false);
    }
  }

  useEffect(() => { document.title = "Logs - Sky Weaver Hub"; }, []);
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, [load]);

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-widest text-muted-foreground">Diagnostics</p>
        <h1 className="text-3xl font-semibold tracking-tight flex items-center gap-3"><ScrollText className="h-7 w-7 text-primary" /> Logs</h1>
      </div>
      <Card className="telemetry-card grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="space-y-2"><Label>Level</Label><Select value={level} onValueChange={setLevel}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["all", "debug", "info", "warning", "error"].map((l) => <SelectItem key={l} value={l}>{l}</SelectItem>)}</SelectContent></Select></div>
        <div className="space-y-2 md:col-span-2"><Label>Source filter</Label><Input value={source} onChange={(e) => setSource(e.target.value)} placeholder="camera, scheduler, api" /></div>
      </Card>
      <Card className="telemetry-card min-w-0 p-0 overflow-hidden">
        <div className="font-mono-data text-xs divide-y divide-border/60">
          {logs.map((l) => (
            <div key={l.id} className="grid grid-cols-2 gap-x-3 gap-y-1 px-4 py-3 hover:bg-muted/30 sm:grid-cols-[170px_76px_120px_minmax(0,1fr)] sm:items-center sm:py-2">
              <span className="text-muted-foreground">{format(new Date(l.created_at), "yyyy-MM-dd HH:mm:ss")}</span>
              <span className={`text-right uppercase tracking-wider sm:text-left ${LEVEL_COLOR[l.level] ?? ""}`}>{l.level}</span>
              <span className="min-w-0 text-primary sm:truncate">{l.source}</span>
              <span className="col-span-2 min-w-0 break-words text-foreground sm:col-span-1 sm:truncate">{l.message}</span>
            </div>
          ))}
          {logs.length === 0 && <p className="p-6 text-sm text-muted-foreground">No log entries.</p>}
        </div>
        {nextCursor && <div className="border-t border-border/60 p-3"><Button variant="outline" className="w-full" onClick={loadMore} disabled={loadingMore}>{loadingMore ? "Loading..." : "Load more"}</Button></div>}
      </Card>
    </div>
  );
}
