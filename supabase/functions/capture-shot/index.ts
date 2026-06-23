// AllSky capture edge function — mock adapter.
// Real adapters (libcamera, gphoto2, INDI, ZWO) should implement the same
// shape: { camera_id, type } -> inserts an `images` row + capture_jobs + event.
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.45.0";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

interface Body { camera_id?: string; type?: "test" | "manual" | "scheduled"; }

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: corsHeaders });

  try {
    const supabase = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    );

    const body: Body = await req.json().catch(() => ({}));
    const type = body.type ?? "test";

    // Resolve camera (default if none)
    let cameraId = body.camera_id;
    if (!cameraId) {
      const { data: cam } = await supabase.from("cameras")
        .select("id").eq("is_default", true).maybeSingle();
      cameraId = cam?.id;
    }
    if (!cameraId) {
      return new Response(JSON.stringify({ error: "no_camera" }), {
        status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    // Load settings for metadata
    const { data: settings } = await supabase.from("camera_settings")
      .select("exposure_us, gain, resolution, file_format, white_balance, binning")
      .eq("camera_id", cameraId).maybeSingle();

    // Create job
    const startedAt = new Date().toISOString();
    const { data: job } = await supabase.from("capture_jobs").insert({
      camera_id: cameraId, type, state: "capturing", started_at: startedAt,
      params: settings ?? {},
    }).select().single();

    await supabase.from("realtime_events").insert({
      type: "capture_started",
      payload: { camera_id: cameraId, job_id: job?.id, kind: type },
    });

    // Simulate small exposure delay (capped so the function returns quickly)
    const exposureMs = Math.min(800, Math.round((settings?.exposure_us ?? 1_000_000) / 1000));
    await new Promise((r) => setTimeout(r, exposureMs));

    // Insert image
    const starCount = 80 + Math.floor(Math.random() * 200);
    const cloudScore = Number((Math.random() * 0.6).toFixed(2));
    const { data: image } = await supabase.from("images").insert({
      camera_id: cameraId,
      captured_at: new Date().toISOString(),
      storage_path: "demo/sample-sky-1.jpg",
      thumb_path: "demo/sample-sky-1.jpg",
      metadata: {
        ...(settings ?? {}),
        source: type,
        adapter: "mock",
        sky_temp_c: -4 + Math.random() * 8,
      },
      tags: type === "test" ? ["test"] : ["capture"],
      star_count: starCount,
      cloud_score: cloudScore,
    }).select().single();

    // Complete job
    await supabase.from("capture_jobs").update({
      state: "idle", ended_at: new Date().toISOString(),
    }).eq("id", job!.id);

    await supabase.from("realtime_events").insert({
      type: "new_image",
      payload: { image_id: image?.id, camera_id: cameraId, kind: type },
    });

    await supabase.from("logs").insert({
      level: "info", source: "capture",
      message: `Captured ${type} image (${starCount} stars, cloud ${cloudScore})`,
      context: { image_id: image?.id, camera_id: cameraId },
    });

    return new Response(JSON.stringify({ ok: true, image, job }), {
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  } catch (e) {
    return new Response(JSON.stringify({ error: String(e) }), {
      status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
