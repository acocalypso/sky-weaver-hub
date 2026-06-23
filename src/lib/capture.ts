import { SkyApi } from "@/lib/api";

export type CaptureType = "test" | "manual" | "scheduled";

export async function triggerCapture(opts: { camera_id?: string; type?: CaptureType } = {}) {
  return SkyApi.testShot({ camera_id: opts.camera_id, mode: opts.type ?? "test" });
}
