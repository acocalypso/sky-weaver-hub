const API_BASE = import.meta.env.VITE_SKYWEAVER_API_BASE ?? "";
const TOKEN_KEY = "skyweaver_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body) headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  const text = await res.text();
  const payload = text ? JSON.parse(text) : {};
  if (!res.ok) throw new Error(payload?.error?.message ?? payload?.detail ?? res.statusText);
  return (payload.data ?? payload) as T;
}

export const SkyApi = {
  login: (username: string, password: string) =>
    api<{ token: string; user: SkyUser }>("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  me: () => api<SkyUserPrincipal>("/api/v1/auth/me"),
  setupStatus: () => api<SetupStatus>("/api/v1/setup/status"),
  completeSetup: (body: SetupComplete) => api<{ required: boolean }>("/api/v1/setup/complete", { method: "POST", body: JSON.stringify(body) }),
  status: () => api<SkyStatus>("/api/v1/status"),
  metrics: () => api<SystemMetrics>("/api/v1/system/metrics"),
  systemServices: () => api<SystemService[]>("/api/v1/system/services"),
  serviceDetail: (name: string) => api<ServiceDetail>(`/api/v1/system/services/${name}`),
  controlService: (name: string, action: ServiceAction) => api<ServiceActionResult>(`/api/v1/system/services/${name}/${action}`, { method: "POST" }),
  restartService: (name: string) => api<ServiceActionResult>(`/api/v1/system/services/${name}/restart`, { method: "POST" }),
  diagnostics: () => api<SystemDiagnostics>("/api/v1/system/diagnostics"),
  logs: (query = "") => api<LogRow[]>(`/api/v1/logs${query}`),
  cameras: () => api<CameraRow[]>("/api/v1/cameras"),
  detectCameras: () => api<DetectedCamera[]>("/api/v1/cameras/detect", { method: "POST" }),
  createCamera: (body: Partial<CameraRow>) => api<{ id: string }>("/api/v1/cameras", { method: "POST", body: JSON.stringify(body) }),
  patchCamera: (id: string, body: Partial<CameraRow>) => api<{ id: string }>(`/api/v1/cameras/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  cameraProfiles: () => api<CameraProfile[]>("/api/v1/camera-profiles"),
  createProfile: (body: { camera_id: string; name: string; mode: string; settings: Record<string, any> }) =>
    api<{ id: string }>("/api/v1/camera-profiles", { method: "POST", body: JSON.stringify(body) }),
  patchProfile: (id: string, settings: any) => api(`/api/v1/camera-profiles/${id}`, { method: "PATCH", body: JSON.stringify({ settings }) }),
  captureStart: () => api("/api/v1/capture/start", { method: "POST" }),
  captureStop: () => api<CaptureStopResult>("/api/v1/capture/stop", { method: "POST" }),
  capturePause: () => api("/api/v1/capture/pause", { method: "POST" }),
  captureResume: () => api("/api/v1/capture/resume", { method: "POST" }),
  testShot: (body: any = {}) => api<CaptureJob>("/api/v1/capture/test-shot", { method: "POST", body: JSON.stringify(body) }),
  queueSingleCapture: (body: any = {}) => api<CaptureJob>("/api/v1/capture/single", { method: "POST", body: JSON.stringify(body) }),
  queueSequenceCapture: (body: any = {}) => api<CaptureJob>("/api/v1/capture/sequence", { method: "POST", body: JSON.stringify(body) }),
  captureJobs: () => api<CaptureJob[]>("/api/v1/capture/jobs"),
  images: (query = "") => api<ImageRow[]>(`/api/v1/images${query}`),
  deleteImage: (id: string) => api<ImageDeleteResult>(`/api/v1/images/${id}`, { method: "DELETE" }),
  runImageRetention: (days?: number) => api<ImageRetentionResult>(`/api/v1/images/retention/run${days === undefined ? "" : `?days=${encodeURIComponent(days)}`}`, { method: "POST" }),
  publicLatest: () => api<PublicLatestImage>("/api/v1/public/latest"),
  settings: () => api<Record<string, any>>("/api/v1/settings"),
  patchSettings: (values: Record<string, any>) => api<Record<string, any>>("/api/v1/settings", { method: "PATCH", body: JSON.stringify({ values }) }),
  schedule: () => api<ScheduleRow>("/api/v1/schedule"),
  putSchedule: (body: ScheduleRow) => api<ScheduleRow>("/api/v1/schedule", { method: "PUT", body: JSON.stringify(body) }),
  schedulePreview: (body: Partial<ScheduleRow> = {}) => api<SchedulePreview>("/api/v1/schedule/preview-tonight", { method: "POST", body: JSON.stringify(body) }),
  products: () => api<ProductRow[]>("/api/v1/products"),
  processingJobs: () => api<ProcessingJob[]>("/api/v1/processing/jobs"),
  createProduct: (type: string, body: any) => api<ProcessingJob>(`/api/v1/products/${type}`, { method: "POST", body: JSON.stringify(body) }),
  apiKeys: () => api<ApiKeyRow[]>("/api/v1/api-keys"),
  createApiKey: (body: { name: string; scopes: string[] }) => api<any>("/api/v1/api-keys", { method: "POST", body: JSON.stringify(body) }),
  patchApiKey: (id: string, body: { enabled?: boolean }) => api<any>(`/api/v1/api-keys/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteApiKey: (id: string) => api<{ deleted: string }>(`/api/v1/api-keys/${id}`, { method: "DELETE" }),
  migrationDetect: () => api<any[]>("/api/v1/migration/allsky/detect"),
};

export interface SkyUser { id: string; username: string; role: string; }
export interface SkyUserPrincipal extends SkyUser { type: string; scopes: string[]; }
export interface SetupStatus { required: boolean; bootstrap_password_active?: boolean; observatory: Record<string, any>; public_page: Record<string, any>; schedule: Partial<ScheduleRow>; cameras: CameraRow[]; }
export interface SetupComplete { admin_password?: string; observatory_name: string; latitude: number; longitude: number; timezone: string; public_page_enabled: boolean; primary_camera_id?: string | null; }
export interface SkyStatus { capture: any; camera: CameraRow | null; latest_image: ImageRow | null; }
export interface SystemMetrics { cpu_percent: number; memory_percent: number; disk_percent: number; disk_free_gb: number; temperature_c: number | null; uptime_seconds: number; }
export type ServiceAction = "start" | "stop" | "restart";
export interface ServiceActionResult { name: string; unit: string; action: ServiceAction; status: string; note: string; }
export interface SystemService { name: string; unit?: string; status: string; managed_by?: string; actions?: ServiceAction[]; heartbeat_at?: string | null; heartbeat_age_seconds?: number | null; pid?: number | null; last_claimed_job_id?: string | null; last_claimed_job_type?: string | null; last_claimed_at?: string | null; last_success_at?: string | null; }
export interface ServiceFailureFinding { level: "ok" | "warning" | "error"; message: string; }
export interface ServiceFailureAnalysis { severity: "ok" | "warning" | "error"; summary: string; findings: ServiceFailureFinding[]; suggested_actions: string[]; }
export interface ServiceUnitHistory { restarts: number | null; result: string | null; exec_main_status: string | null; recent_events: { label: string; value: string }[]; }
export interface ServiceDetail { service: SystemService; unit: string; properties: Record<string, string>; systemctl_status: string; systemctl_error?: string | null; journal: string[]; journal_status: string; journal_error?: string | null; failure_analysis?: ServiceFailureAnalysis; unit_history?: ServiceUnitHistory; }
export interface SystemDiagnostics { generated_at: string; app: Record<string, any>; platform: Record<string, any>; paths: Record<string, string>; database: Record<string, any>; metrics: SystemMetrics; services: SystemService[]; counts: Record<string, number>; recent_logs: LogRow[]; redaction: string; }
export interface CaptureStopResult { status: string; stop_mode: "graceful"; canceled_jobs: number; in_progress_jobs: number; in_progress_job_ids: string[]; adapter_cancel_mode: "best_effort"; cancel_requested_jobs: number; cancel_requested_job_ids: string[]; message: string; }
export interface CameraRow { id: string; name: string; adapter: string; device_id?: string | null; model?: string | null; serial?: string | null; enabled: boolean; is_primary: boolean; capabilities?: any; created_at?: string; updated_at?: string; }
export interface DetectedCamera { id: string; name: string; backend: string; model?: string | null; serial?: string | null; metadata?: any; }
export interface CameraProfile { id: string; camera_id: string; name: string; mode: string; settings: Record<string, any>; }
export interface ImageRow { id: string; camera_id: string | null; captured_at: string; day_key: string; mode: string; file_path: string; public_url: string | null; thumbnail_path: string | null; format: string; width: number | null; height: number | null; size_bytes: number | null; exposure_ms: number | null; gain: number | null; temperature_c: number | null; mean_brightness: number | null; star_count: number | null; cloud_score: number | null; bad_image: boolean; metadata: any; }
export interface ImageSkippedFile { path: string; status: "skipped"; reason?: string; }
export interface ImageDeleteResult { deleted: string; deleted_files: string[]; missing_files: string[]; skipped_files: ImageSkippedFile[]; latest_republished?: PublicLatestImage | null; }
export interface ImageRetentionResult { retention_days: number; cutoff: string; deleted_images: number; deleted_image_ids: string[]; deleted_files: string[]; missing_files: string[]; skipped_files: ImageSkippedFile[]; }
export interface PublicLatestImage { id: string; captured_at: string; day_key: string; mode: string; format: string; width: number | null; height: number | null; size_bytes: number | null; exposure_ms?: number | null; gain?: number | null; camera_id?: string | null; download_url: string; metadata_url: string; thumbnail_url?: string | null; latest_file?: string; latest_thumbnail_file?: string; }
export interface ScheduleRow { id?: string; enabled: boolean; start_mode: string; end_mode: string; sun_angle: number; fixed_start_time?: string | null; fixed_end_time?: string | null; timezone: string; latitude: number; longitude: number; interval_seconds: number; exposure_ramping_enabled: boolean; }
export interface SchedulePreview {
  enabled: boolean;
  active: boolean;
  now: string;
  window_start: string | null;
  window_end: string | null;
  next_transition_at: string | null;
  next_state: string;
  timezone: string;
  capture_mode?: "day" | "night";
  capture_enabled?: boolean;
  save_enabled?: boolean;
  interval_seconds?: number | null;
  last_scheduled_capture_at?: string | null;
  next_capture_due_at?: string | null;
  capture_due?: boolean;
  seconds_until_due?: number | null;
}
export interface ProductRow { id: string; type: string; day_key: string; file_path: string | null; thumbnail_path: string | null; status: string; metadata: any; created_at: string; }
export interface ProcessingJob { id: string; type: string; status: string; input: any; output?: any; error?: string | null; progress: number; created_at: string; started_at?: string | null; completed_at?: string | null; }
export interface CaptureJob { id: string; type: string; status: string; request: any; result?: any; error?: string | null; progress: number; created_at: string; started_at?: string | null; completed_at?: string | null; }
export interface LogRow { id: string; level: string; source: string; message: string; context: any; created_at: string; }
export interface ApiKeyRow { id: string; name: string; prefix: string; scopes: string[]; enabled: boolean; created_at: string; last_used_at?: string | null; }
