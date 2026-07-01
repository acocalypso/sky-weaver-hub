import { useEffect, useState } from "react";
import sampleSky from "@/assets/sample-sky-1.jpg";
import { getToken } from "@/lib/api";

type AuthenticatedImageProps = React.ImgHTMLAttributes<HTMLImageElement> & {
  src: string | null | undefined;
  fallbackSrc?: string;
};

export function AuthenticatedImage({ src, fallbackSrc = sampleSky, alt, ...props }: AuthenticatedImageProps) {
  const [resolvedSrc, setResolvedSrc] = useState(fallbackSrc);

  useEffect(() => {
    if (!src) {
      setResolvedSrc(fallbackSrc);
      return;
    }
    let ignore = false;
    let objectUrl: string | null = null;

    async function load() {
      try {
        const token = getToken();
        const headers = token ? { Authorization: `Bearer ${token}` } : undefined;
        const response = await fetch(src, { headers });
        if (!response.ok) throw new Error(response.statusText);
        const blob = await response.blob();
        const nextObjectUrl = URL.createObjectURL(blob);
        if (ignore) {
          URL.revokeObjectURL(nextObjectUrl);
          return;
        }
        objectUrl = nextObjectUrl;
        setResolvedSrc(nextObjectUrl);
      } catch {
        if (!ignore) setResolvedSrc(fallbackSrc);
      }
    }

    void load();
    return () => {
      ignore = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [src, fallbackSrc]);

  return <img src={resolvedSrc} alt={alt} {...props} />;
}
