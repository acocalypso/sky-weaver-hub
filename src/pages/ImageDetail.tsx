import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { format } from "date-fns";
import { ArrowLeft, Download, ImageIcon, Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/StatusBadge";
import { SkyApi, getToken, type ImageRow } from "@/lib/api";
import sampleSky from "@/assets/sample-sky-1.jpg";

export default function ImageDetail() {
  const { imageId } = useParams();
  const [image, setImage] = useState<ImageRow | null>(null);
  const [imageUrl, setImageUrl] = useState(sampleSky);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    document.title = "Image detail - Sky Weaver Hub";
  }, []);

  useEffect(() => {
    let ignore = false;
    async function load() {
      if (!imageId) return;
      setLoading(true);
      try {
        const next = await SkyApi.imageDetail(imageId);
        if (!ignore) setImage(next);
      } catch (e: any) {
        if (!ignore) toast.error(e.message ?? "Unable to load image");
      } finally {
        if (!ignore) setLoading(false);
      }
    }
    void load();
    return () => {
      ignore = true;
    };
  }, [imageId]);

  useEffect(() => {
    if (!image) return;
    let ignore = false;
    let objectUrl: string | null = null;
    async function loadImageBlob() {
      try {
        const token = getToken();
        const headers = token ? { Authorization: `Bearer ${token}` } : undefined;
        const response = await fetch(image.public_url ?? `/api/v1/images/${image.id}/download`, { headers });
        if (!response.ok) throw new Error(response.statusText);
        const blob = await response.blob();
        objectUrl = URL.createObjectURL(blob);
        if (!ignore) setImageUrl(objectUrl);
      } catch {
        if (!ignore) setImageUrl(sampleSky);
      }
    }
    void loadImageBlob();
    return () => {
      ignore = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [image]);

  const apiPreview = useMemo(() => image && {
    id: image.id,
    captured_at: image.captured_at,
    camera_id: image.camera_id,
    download: `/api/v1/images/${image.id}/download`,
    quality: { mean_brightness: image.mean_brightness, star_count: image.star_count, cloud_score: image.cloud_score, bad_image: image.bad_image },
    metadata: image.metadata,
  }, [image]);

  async function deleteImage() {
    if (!image || deleting) return;
    setDeleting(true);
    try {
      const result = await SkyApi.deleteImage(image.id);
      toast.success(`Deleted image and ${result.deleted_files.length} file${result.deleted_files.length === 1 ? "" : "s"}`);
      setImage(null);
    } catch (e: any) {
      toast.error(e.message ?? "Delete failed");
    } finally {
      setDeleting(false);
    }
  }

  if (loading) {
    return (
      <div className="grid min-h-[40vh] place-items-center text-sm text-muted-foreground">
        <div className="flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" /> Loading image</div>
      </div>
    );
  }

  if (!image) {
    return (
      <div className="space-y-6">
        <Button asChild variant="outline" size="sm"><Link to="/gallery"><ArrowLeft className="h-4 w-4 mr-2" />Gallery</Link></Button>
        <Card className="telemetry-card text-sm text-muted-foreground">Image not found or unavailable.</Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <Button asChild variant="outline" size="sm" className="mb-4"><Link to="/gallery"><ArrowLeft className="h-4 w-4 mr-2" />Gallery</Link></Button>
          <p className="text-xs uppercase tracking-widest text-muted-foreground">Archive</p>
          <h1 className="flex items-center gap-3 text-3xl font-semibold tracking-tight">
            <ImageIcon className="h-7 w-7 text-primary" /> Image detail
          </h1>
          <p className="mt-2 font-mono-data text-xs text-muted-foreground">{formatDate(image.captured_at)} - {image.id}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline"><a href={imageUrl} download={`${image.day_key}-${image.id}.${image.format.toLowerCase()}`}><Download className="h-4 w-4 mr-2" />Download</a></Button>
          <Button variant="destructive" onClick={deleteImage} disabled={deleting}><Trash2 className="h-4 w-4 mr-2" />{deleting ? "Deleting" : "Delete"}</Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(20rem,0.65fr)]">
        <Card className="overflow-hidden rounded-md border border-border bg-black">
          <img src={imageUrl} alt={`All-sky capture ${image.id}`} className="h-full max-h-[70vh] min-h-[18rem] w-full object-contain" />
        </Card>
        <div className="space-y-4">
          <Card className="telemetry-card space-y-3">
            <div className="flex flex-wrap gap-2">
              <StatusBadge variant="active">{image.mode}</StatusBadge>
              {image.bad_image && <StatusBadge variant="error">bad image</StatusBadge>}
              {image.overlay_applied && <StatusBadge variant="ok">overlay</StatusBadge>}
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-1">
              <Stat label="Captured" value={formatDate(image.captured_at)} />
              <Stat label="Camera" value={image.camera_id ?? "-"} />
              <Stat label="Format" value={image.format?.toUpperCase()} />
              <Stat label="Dimensions" value={formatDimensions(image)} />
              <Stat label="Size" value={formatBytes(image.size_bytes)} />
              <Stat label="Exposure ms" value={image.exposure_ms} />
              <Stat label="Gain" value={image.gain} />
              <Stat label="Mean brightness" value={image.mean_brightness} />
              <Stat label="Stars" value={image.star_count} />
              <Stat label="Cloud score" value={image.cloud_score} />
            </div>
          </Card>
          <Card className="telemetry-card">
            <p className="mb-2 text-xs uppercase tracking-widest text-muted-foreground">API response</p>
            <pre className="max-h-80 overflow-auto rounded-md bg-muted/40 p-3 font-mono-data text-[11px]">{JSON.stringify(apiPreview, null, 2)}</pre>
          </Card>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: any }) {
  return <div className="flex justify-between gap-3 rounded-md bg-muted/30 p-2"><span className="text-xs uppercase tracking-widest text-muted-foreground">{label}</span><span className="min-w-0 truncate font-mono-data">{value ?? "-"}</span></div>;
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? format(date, "yyyy-MM-dd HH:mm:ss") : value;
}

function formatDimensions(image: ImageRow) {
  const width = image.metadata?.storage?.image?.width ?? image.width;
  const height = image.metadata?.storage?.image?.height ?? image.height;
  return width && height ? `${width} x ${height}` : "-";
}

function formatBytes(value?: number | null) {
  if (!value) return "-";
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}
