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
  status: () => api<SkyStatus>("/api/v1/status"),
  metrics: () => api<SystemMetrics>("/api/v1/system/metrics"),
  logs: (query = "") => api<LogRow[]>(`/api/v1/logs${query}`),
  cameras: () => api<CameraRow[]>("/api/v1/cameras"),
  detectCameras: () => api<DetectedCamera[]>("/api/v1/cameras/detect", { method: "POST" }),
  createCamera: (body: Partial<CameraRow>) => api<{ id: string }>("/api/v1/cameras", { method: "POST", body: JSON.stringify(body) }),
  patchCamera: (id: string, body: Partial<CameraRow>) => api<{ id: string }>(`/api/v1/cameras/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  cameraProfiles: () => api<CameraProfile[]>("/api/v1/camera-profiles"),
  patchProfile: (id: string, settings: any) => api(`/api/v1/camera-profiles/${id}`, { method: "PATCH", body: JSON.stringify({ settings }) }),
  captureStart: () => api("/api/v1/capture/start", { method: "POST" }),
  captureStop: () => api("/api/v1/capture/stop", { method: "POST" }),
  testShot: (body: any = {}) => api<any>("/api/v1/capture/test-shot", { method: "POST", body: JSON.stringify(body) }),
  images: (query = "") => api<ImageRow[]>(`/api/v1/images${query}`),
  settings: () => api<Record<string, any>>("/api/v1/settings"),
  patchSettings: (values: Record<string, any>) => api<Record<string, any>>("/api/v1/settings", { method: "PATCH", body: JSON.stringify({ values }) }),
  schedule: () => api<ScheduleRow>("/api/v1/schedule"),
  putSchedule: (body: ScheduleRow) => api<ScheduleRow>("/api/v1/schedule", { method: "PUT", body: JSON.stringify(body) }),
  products: () => api<any[]>("/api/v1/products"),
  createProduct: (type: string, body: any) => api<any>(`/api/v1/products/${type}`, { method: "POST", body: JSON.stringify(body) }),
  apiKeys: () => api<ApiKeyRow[]>("/api/v1/api-keys"),
  createApiKey: (body: { name: string; scopes: string[] }) => api<any>("/api/v1/api-keys", { method: "POST", body: JSON.stringify(body) }),
  migrationDetect: () => api<any[]>("/api/v1/migration/allsky/detect"),
};

export interface SkyUser { id: string; username: string; role: string; }
export interface SkyUserPrincipal extends SkyUser { type: string; scopes: string[]; }
export interface SkyStatus { capture: any; camera: CameraRow | null; latest_image: ImageRow | null; }
export interface SystemMetrics { cpu_percent: number; memory_percent: number; disk_percent: number; disk_free_gb: number; temperature_c: number | null; uptime_seconds: number; }
export interface CameraRow { id: string; name: string; adapter: string; device_id?: string | null; model?: string | null; serial?: string | null; enabled: boolean; is_primary: boolean; capabilities?: any; created_at?: string; updated_at?: string; }
export interface DetectedCamera { id: string; name: string; backend: string; model?: string | null; serial?: string | null; metadata?: any; }
export interface CameraProfile { id: string; camera_id: string; name: string; mode: string; settings: Record<string, any>; }
export interface ImageRow { id: string; camera_id: string | null; captured_at: string; day_key: string; mode: string; file_path: string; public_url: string | null; thumbnail_path: string | null; format: string; width: number | null; height: number | null; size_bytes: number | null; exposure_ms: number | null; gain: number | null; temperature_c: number | null; mean_brightness: number | null; star_count: number | null; cloud_score: number | null; bad_image: boolean; metadata: any; }
export interface ScheduleRow { id?: string; enabled: boolean; start_mode: string; end_mode: string; sun_angle: number; fixed_start_time?: string | null; fixed_end_time?: string | null; timezone: string; latitude: number; longitude: number; interval_seconds: number; exposure_ramping_enabled: boolean; }
export interface LogRow { id: string; level: string; source: string; message: string; context: any; created_at: string; }
export interface ApiKeyRow { id: string; name: string; prefix: string; scopes: string[]; enabled: boolean; created_at: string; last_used_at?: string | null; }
