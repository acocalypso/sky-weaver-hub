import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/StatusBadge";
import { SkyApi, type ImageRow } from "@/lib/api";
import sampleSky from "@/assets/sample-sky-1.jpg";
import { format } from "date-fns";
import { Images, Tag, Trash2 } from "lucide-react";
import { toast } from "sonner";

export default function Gallery() {
  const [images, setImages] = useState<ImageRow[]>([]);
  const [date, setDate] = useState<string>("");
  const [mode, setMode] = useState<string>("all");
  const [quality, setQuality] = useState<string>("any");
  const [selected, setSelected] = useState<ImageRow | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    const params = new URLSearchParams({ limit: "200" });
    if (date) params.set("day_key", date.replaceAll("-", ""));
    if (mode !== "all") params.set("mode", mode);
    try {
      const rows = await SkyApi.images(`?${params}`);
      setImages(rows.filter((img) => quality === "any" || (quality === "bad" ? img.bad_image : !img.bad_image)));
    } catch (e: any) {
      toast.error(e.message ?? "Unable to load images");
    }
  }, [date, mode, quality]);

  useEffect(() => { document.title = "Gallery - Sky Weaver Hub"; }, []);
  useEffect(() => { load(); }, [load]);

  const apiPreview = useMemo(() => selected && {
    id: selected.id,
    captured_at: selected.captured_at,
    camera_id: selected.camera_id,
    download: `/api/v1/images/${selected.id}/download`,
    metadata: selected.metadata,
    quality: { mean_brightness: selected.mean_brightness, star_count: selected.star_count, cloud_score: selected.cloud_score, bad_image: selected.bad_image },
  }, [selected]);

  async function deleteSelected() {
    if (!selected || deleting) return;
    setDeleting(true);
    try {
      const result = await SkyApi.deleteImage(selected.id);
      toast.success(`Deleted image and ${result.deleted_files.length} file${result.deleted_files.length === 1 ? "" : "s"}`);
      setSelected(null);
      await load();
    } catch (e: any) {
      toast.error(e.message ?? "Delete failed");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-widest text-muted-foreground">Archive</p>
        <h1 className="text-3xl font-semibold tracking-tight flex items-center gap-3"><Images className="h-7 w-7 text-primary" /> Image gallery</h1>
      </div>

      <Card className="telemetry-card grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="space-y-2"><Label>Date</Label><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></div>
        <div className="space-y-2"><Label>Mode</Label><Select value={mode} onValueChange={setMode}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["all", "day", "night", "manual"].map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent></Select></div>
        <div className="space-y-2"><Label>Quality</Label><Select value={quality} onValueChange={setQuality}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="any">Any</SelectItem><SelectItem value="good">Good only</SelectItem><SelectItem value="bad">Bad image</SelectItem></SelectContent></Select></div>
        <div className="flex items-end"><Button variant="outline" className="w-full" onClick={() => { setDate(""); setMode("all"); setQuality("any"); }}>Reset filters</Button></div>
      </Card>

      <p className="text-xs text-muted-foreground font-mono-data">{images.length} image{images.length === 1 ? "" : "s"}</p>

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
        {images.map((img) => (
          <button key={img.id} onClick={() => setSelected(img)} className="group relative aspect-square rounded-md overflow-hidden border border-border bg-muted/40">
            <img src={img.public_url ?? sampleSky} loading="lazy" alt="" className="w-full h-full object-cover opacity-90 group-hover:opacity-100 group-hover:scale-105 transition" />
            <div className="absolute bottom-0 left-0 right-0 p-1.5 bg-gradient-to-t from-background/95 to-transparent">
              <p className="text-[10px] font-mono-data">{format(new Date(img.captured_at), "MM-dd HH:mm")}</p>
              <p className="text-[9px] text-muted-foreground">mean {img.mean_brightness ?? "-"} - {img.mode}</p>
            </div>
          </button>
        ))}
        {images.length === 0 && <p className="col-span-full text-sm text-muted-foreground">No images match these filters.</p>}
      </div>

      <Dialog open={!!selected} onOpenChange={(o) => !o && setSelected(null)}>
        <DialogContent className="max-w-4xl">
          <DialogHeader><DialogTitle className="font-mono-data text-sm">{selected && format(new Date(selected.captured_at), "yyyy-MM-dd HH:mm:ss")}</DialogTitle></DialogHeader>
          {selected && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="aspect-square rounded-md overflow-hidden bg-black"><img src={selected.public_url ?? sampleSky} alt="" className="w-full h-full object-cover" /></div>
              <div className="space-y-3 text-sm">
                <div className="flex flex-wrap gap-2">
                  <StatusBadge variant="active"><Tag className="h-3 w-3 mr-1" />{selected.mode}</StatusBadge>
                  {selected.bad_image && <StatusBadge variant="error">bad image</StatusBadge>}
                </div>
                <Stat label="Exposure ms" value={selected.exposure_ms} />
                <Stat label="Gain" value={selected.gain} />
                <Stat label="Mean brightness" value={selected.mean_brightness} />
                <Stat label="Size bytes" value={selected.size_bytes} />
                <Stat label="Format" value={selected.metadata?.storage?.image?.format ?? selected.format?.toUpperCase()} />
                <Stat label="Dimensions" value={formatDimensions(selected)} />
                <Stat label="EXIF tags" value={Object.keys(selected.metadata?.storage?.exif ?? {}).length} />
                <div>
                  <p className="text-xs uppercase tracking-widest text-muted-foreground mb-1">API response</p>
                  <pre className="text-[11px] font-mono-data bg-muted/40 p-3 rounded-md overflow-auto max-h-72">{JSON.stringify(apiPreview, null, 2)}</pre>
                </div>
                <Button type="button" variant="destructive" className="w-full" onClick={deleteSelected} disabled={deleting}>
                  <Trash2 className="h-4 w-4 mr-2" />{deleting ? "Deleting..." : "Delete image"}
                </Button>
                <Button asChild type="button" variant="outline" className="w-full">
                  <Link to={`/gallery/${selected.id}`}>Open detail page</Link>
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: any }) {
  return <div className="flex justify-between p-2 rounded-md bg-muted/30"><span className="text-xs uppercase tracking-widest text-muted-foreground">{label}</span><span className="font-mono-data">{value ?? "-"}</span></div>;
}

function formatDimensions(image: ImageRow) {
  const width = image.metadata?.storage?.image?.width ?? image.width;
  const height = image.metadata?.storage?.image?.height ?? image.height;
  return width && height ? `${width} x ${height}` : "-";
}
