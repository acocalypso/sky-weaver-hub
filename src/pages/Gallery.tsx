import { useEffect, useMemo, useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/StatusBadge";
import sampleSky from "@/assets/sample-sky-1.jpg";
import { format } from "date-fns";
import { Images, Tag } from "lucide-react";

interface ImageRow {
  id: string; captured_at: string; storage_path: string; metadata: any;
  star_count: number | null; cloud_score: number | null; tags: string[];
  camera_id: string | null;
}

export default function Gallery() {
  const [images, setImages] = useState<ImageRow[]>([]);
  const [date, setDate] = useState<string>("");
  const [tag, setTag] = useState<string>("all");
  const [sky, setSky] = useState<string>("any");
  const [selected, setSelected] = useState<ImageRow | null>(null);

  useEffect(() => { document.title = "Gallery · AllSky Control Hub"; }, []);

  useEffect(() => {
    let query = supabase.from("images")
      .select("id, captured_at, storage_path, metadata, star_count, cloud_score, tags, camera_id")
      .order("captured_at", { ascending: false }).limit(200);
    if (date) {
      const start = new Date(date + "T00:00:00").toISOString();
      const end = new Date(date + "T23:59:59").toISOString();
      query = query.gte("captured_at", start).lte("captured_at", end);
    }
    if (tag !== "all") query = query.contains("tags", [tag]);
    if (sky === "clear") query = query.lt("cloud_score", 0.3);
    if (sky === "cloudy") query = query.gte("cloud_score", 0.3);

    query.then(({ data }) => setImages((data ?? []) as ImageRow[]));

    const ch = supabase.channel("gallery-realtime")
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "images" }, (p) => {
        setImages((cur) => [p.new as ImageRow, ...cur].slice(0, 200));
      }).subscribe();
    return () => { supabase.removeChannel(ch); };
  }, [date, tag, sky]);

  const apiPreview = useMemo(() => selected && {
    id: selected.id,
    captured_at: selected.captured_at,
    camera_id: selected.camera_id,
    url: `/api/v1/images/${selected.id}/file`,
    metadata: selected.metadata,
    quality: { star_count: selected.star_count, cloud_score: selected.cloud_score },
    tags: selected.tags,
  }, [selected]);

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-widest text-muted-foreground">Archive</p>
        <h1 className="text-3xl font-semibold tracking-tight flex items-center gap-3"><Images className="h-7 w-7 text-primary" /> Image gallery</h1>
      </div>

      <Card className="telemetry-card grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="space-y-2">
          <Label>Date</Label>
          <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </div>
        <div className="space-y-2">
          <Label>Tag</Label>
          <Select value={tag} onValueChange={setTag}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="night">Night</SelectItem>
              <SelectItem value="test">Test</SelectItem>
              <SelectItem value="capture">Capture</SelectItem>
              <SelectItem value="demo">Demo</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label>Sky</Label>
          <Select value={sky} onValueChange={setSky}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="any">Any conditions</SelectItem>
              <SelectItem value="clear">Clear (cloud &lt; 0.3)</SelectItem>
              <SelectItem value="cloudy">Cloudy (cloud ≥ 0.3)</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-end">
          <Button variant="outline" className="w-full" onClick={() => { setDate(""); setTag("all"); setSky("any"); }}>Reset filters</Button>
        </div>
      </Card>

      <p className="text-xs text-muted-foreground font-mono-data">{images.length} image{images.length === 1 ? "" : "s"}</p>

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
        {images.map((img) => (
          <button key={img.id} onClick={() => setSelected(img)}
            className="group relative aspect-square rounded-md overflow-hidden border border-border bg-muted/40">
            <img src={sampleSky} loading="lazy" width={300} height={300} alt=""
              className="w-full h-full object-cover opacity-90 group-hover:opacity-100 group-hover:scale-105 transition" />
            <div className="absolute bottom-0 left-0 right-0 p-1.5 bg-gradient-to-t from-background/95 to-transparent">
              <p className="text-[10px] font-mono-data">{format(new Date(img.captured_at), "MM-dd HH:mm")}</p>
              <p className="text-[9px] text-muted-foreground">★ {img.star_count ?? "—"} · ☁ {img.cloud_score ?? "—"}</p>
            </div>
          </button>
        ))}
        {images.length === 0 && <p className="col-span-full text-sm text-muted-foreground">No images match these filters.</p>}
      </div>

      <Dialog open={!!selected} onOpenChange={(o) => !o && setSelected(null)}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle className="font-mono-data text-sm">
              {selected && format(new Date(selected.captured_at), "yyyy-MM-dd HH:mm:ss")}
            </DialogTitle>
          </DialogHeader>
          {selected && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="aspect-square rounded-md overflow-hidden bg-black">
                <img src={sampleSky} alt="" className="w-full h-full object-cover" />
              </div>
              <div className="space-y-3 text-sm">
                <div className="flex flex-wrap gap-2">
                  {selected.tags.map((t) => <StatusBadge key={t} variant="active"><Tag className="h-3 w-3 mr-1" />{t}</StatusBadge>)}
                </div>
                <Stat label="Stars" value={selected.star_count} />
                <Stat label="Cloud score" value={selected.cloud_score} />
                <div>
                  <p className="text-xs uppercase tracking-widest text-muted-foreground mb-1">API response</p>
                  <pre className="text-[11px] font-mono-data bg-muted/40 p-3 rounded-md overflow-auto max-h-72">
{JSON.stringify(apiPreview, null, 2)}
                  </pre>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: any }) {
  return (
    <div className="flex justify-between p-2 rounded-md bg-muted/30">
      <span className="text-xs uppercase tracking-widest text-muted-foreground">{label}</span>
      <span className="font-mono-data">{value ?? "—"}</span>
    </div>
  );
}
