import { supabase } from "@/integrations/supabase/client";

export type CaptureType = "test" | "manual" | "scheduled";

export async function triggerCapture(opts: { camera_id?: string; type?: CaptureType } = {}) {
  const { data, error } = await supabase.functions.invoke("capture-shot", {
    body: { camera_id: opts.camera_id, type: opts.type ?? "test" },
  });
  if (error) throw error;
  return data as { ok: boolean; image: any; job: any };
}
