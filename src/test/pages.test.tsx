import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Dashboard from "@/pages/Dashboard";
import Gallery from "@/pages/Gallery";
import SettingsPage from "@/pages/Settings";
import ApiKeys from "@/pages/ApiKeys";
import SetupPage from "@/pages/Setup";
import Health from "@/pages/Health";
import PublicSky from "@/pages/PublicSky";
import { SkyApi } from "@/lib/api";

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    message: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    SkyApi: {
      status: vi.fn(),
      images: vi.fn(),
      settings: vi.fn(),
      metrics: vi.fn(),
      systemServices: vi.fn(),
      serviceDetail: vi.fn(),
      diagnostics: vi.fn(),
      controlService: vi.fn(),
      restartService: vi.fn(),
      schedulePreview: vi.fn(),
      captureJobs: vi.fn(),
      apiKeys: vi.fn(),
      patchSettings: vi.fn(),
      createApiKey: vi.fn(),
      patchApiKey: vi.fn(),
      deleteApiKey: vi.fn(),
      setupStatus: vi.fn(),
      completeSetup: vi.fn(),
      detectCameras: vi.fn(),
      createCamera: vi.fn(),
      publicLatest: vi.fn(),
    },
  };
});

const mockImage = {
  id: "img-1",
  camera_id: "cam-1",
  captured_at: "2026-06-23T22:15:00+00:00",
  day_key: "20260623",
  mode: "night",
  file_path: "/data/images/one.jpg",
  public_url: "/api/v1/images/img-1/download",
  thumbnail_path: "/data/thumbnails/one.jpg",
  format: "jpg",
  width: 1280,
  height: 960,
  size_bytes: 12345,
  exposure_ms: 1000,
  gain: 2,
  temperature_c: 21.4,
  mean_brightness: 0.42,
  star_count: null,
  cloud_score: null,
  bad_image: false,
  metadata: { camera: { adapter: "mock" } },
};

const mockSettings = {
  observatory: { name: "Test Observatory", latitude: 47.1, longitude: 15.4, timezone: "Europe/Berlin" },
  storage: { images: "./data/images", videos: "./data/videos", retention_days: 30, min_free_gb: 2 },
  public_page: { enabled: true, iframe_enabled: true },
  security: { cors_origins: ["http://localhost:8080"], first_setup_required: true },
};

const mockPublicLatest = {
  id: "img-1",
  captured_at: "2026-06-23T22:15:00+00:00",
  day_key: "20260623",
  mode: "night",
  format: "jpg",
  width: 1280,
  height: 960,
  size_bytes: 12345,
  camera_id: "cam-1",
  download_url: "/api/v1/public/latest/download",
  metadata_url: "/api/v1/public/latest",
  thumbnail_url: "/api/v1/public/latest/thumbnail",
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(SkyApi.status).mockResolvedValue({
    capture: { status: "running", current_mode: "automation", daemon_last_success_at: "2026-06-23T22:16:00+00:00" },
    camera: { id: "cam-1", name: "Mock all-sky camera", adapter: "mock", enabled: true, is_primary: true },
    latest_image: mockImage,
  } as any);
  vi.mocked(SkyApi.images).mockResolvedValue([mockImage] as any);
  vi.mocked(SkyApi.settings).mockResolvedValue(mockSettings);
  vi.mocked(SkyApi.metrics).mockResolvedValue({ cpu_percent: 12, memory_percent: 34, disk_percent: 45, disk_free_gb: 12.3, temperature_c: 41, uptime_seconds: 7200 });
  vi.mocked(SkyApi.systemServices).mockResolvedValue([
    { name: "skyweaver", unit: "skyweaver.target", status: "running", managed_by: "systemd", actions: ["start", "stop", "restart"] },
    { name: "skyweaver-api", unit: "skyweaver-api.service", status: "running", managed_by: "systemd", actions: ["start", "stop", "restart"] },
    { name: "skyweaver-capture", unit: "skyweaver-capture.service", status: "running", managed_by: "systemd", actions: ["start", "stop", "restart"], heartbeat_at: "2026-06-23T22:16:00+00:00" },
    { name: "skyweaver-worker", unit: "skyweaver-worker.service", status: "idle", managed_by: "systemd", actions: ["start", "stop", "restart"] },
  ]);
  vi.mocked(SkyApi.serviceDetail).mockResolvedValue({
    service: { name: "skyweaver-capture", unit: "skyweaver-capture.service", status: "running", managed_by: "systemd" },
    unit: "skyweaver-capture.service",
    properties: { ActiveState: "active", MainPID: "123" },
    systemctl_status: "ok",
    journal: ["2026-06-24T05:00:00 skyweaver-capture started"],
    journal_status: "ok",
  });
  vi.mocked(SkyApi.diagnostics).mockResolvedValue({
    generated_at: "2026-06-23T22:16:00+00:00",
    app: { name: "Sky Weaver Hub" },
    platform: { system: "Linux", release: "test", python: "3.12" },
    paths: {},
    database: { size_bytes: 2048 },
    metrics: { cpu_percent: 12, memory_percent: 34, disk_percent: 45, disk_free_gb: 12.3, temperature_c: 41, uptime_seconds: 7200 },
    services: [],
    counts: { images: 1, products: 0, capture_jobs_pending: 0, capture_jobs_running: 0, processing_jobs_pending: 0, processing_jobs_running: 0 },
    recent_logs: [],
    redaction: "Secrets redacted",
  });
  vi.mocked(SkyApi.controlService).mockResolvedValue({ name: "skyweaver-capture", unit: "skyweaver-capture.service", action: "restart", status: "completed", note: "restart completed" });
  vi.mocked(SkyApi.schedulePreview).mockResolvedValue({
    enabled: true,
    active: true,
    now: "2026-06-23T22:15:00+00:00",
    window_start: "2026-06-23T20:00:00+00:00",
    window_end: "2026-06-24T04:00:00+00:00",
    next_transition_at: "2026-06-24T04:00:00+00:00",
    next_state: "inactive",
    timezone: "Europe/Berlin",
  });
  vi.mocked(SkyApi.captureJobs).mockResolvedValue([
    { id: "job-1", type: "single", status: "completed", request: { exposure_ms: 1000, gain: 2 }, progress: 1, created_at: "2026-06-23T22:00:00+00:00", result: { image_id: "img-1" } },
  ] as any);
  vi.mocked(SkyApi.apiKeys).mockResolvedValue([
    { id: "key-1", name: "Mobile app", prefix: "swh_1234", scopes: ["read:status", "read:images"], enabled: true, created_at: "2026-06-23T12:00:00+00:00" },
  ]);
  vi.mocked(SkyApi.setupStatus).mockResolvedValue({
    required: true,
    bootstrap_password_active: true,
    observatory: mockSettings.observatory,
    public_page: mockSettings.public_page,
    schedule: { timezone: "Europe/Berlin", latitude: 47.1, longitude: 15.4 },
    cameras: [{ id: "cam-1", name: "Mock all-sky camera", adapter: "mock", enabled: true, is_primary: true }],
  } as any);
  vi.mocked(SkyApi.completeSetup).mockResolvedValue({ required: false });
  vi.mocked(SkyApi.detectCameras).mockResolvedValue([]);
  vi.mocked(SkyApi.createCamera).mockResolvedValue({ id: "cam-2" });
  vi.mocked(SkyApi.publicLatest).mockResolvedValue(mockPublicLatest);
});

describe("main pages", () => {
  it("renders dashboard telemetry from the API", async () => {
    render(<Dashboard />);

    expect(await screen.findByRole("heading", { name: "Test Observatory" })).toBeInTheDocument();
    expect(screen.getByText("Mock all-sky camera")).toBeInTheDocument();
    expect(screen.getByText("Recent captures")).toBeInTheDocument();
    expect(screen.getByText("single")).toBeInTheDocument();
  });

  it("renders gallery images and filters", async () => {
    render(<Gallery />);

    expect(await screen.findByRole("heading", { name: /image gallery/i })).toBeInTheDocument();
    expect(screen.getByText("1 image")).toBeInTheDocument();
    expect(screen.getByText(/mean 0.42 - night/i)).toBeInTheDocument();
  });

  it("renders settings groups from backend settings", async () => {
    render(<SettingsPage />);

    expect(await screen.findByDisplayValue("Test Observatory")).toBeInTheDocument();
    expect(screen.getByText("Storage and retention")).toBeInTheDocument();
    expect(screen.getByText("Public and API")).toBeInTheDocument();
  });

  it("renders API key rows", async () => {
    render(<ApiKeys />);

    expect(await screen.findByRole("heading", { name: /api keys/i })).toBeInTheDocument();
    expect(screen.getByText("Mobile app")).toBeInTheDocument();
    expect(screen.getByText("swh_1234")).toBeInTheDocument();
    expect(screen.getByText("read:images")).toBeInTheDocument();
    await waitFor(() => expect(SkyApi.apiKeys).toHaveBeenCalled());
  });

  it("runs service controls from health", async () => {
    render(<Health />);

    const serviceName = await screen.findByText("skyweaver-capture");
    const serviceRow = serviceName.closest(".rounded-md") as HTMLElement;
    fireEvent.click(within(serviceRow).getByRole("button", { name: /restart/i }));

    await waitFor(() => expect(SkyApi.controlService).toHaveBeenCalledWith("skyweaver-capture", "restart"));
  });

  it("opens service detail journal from health", async () => {
    render(<Health />);

    const serviceName = await screen.findByText("skyweaver-capture");
    const serviceRow = serviceName.closest(".rounded-md") as HTMLElement;
    fireEvent.click(within(serviceRow).getByRole("button", { name: /details/i }));

    expect(await screen.findByText("skyweaver-capture details")).toBeInTheDocument();
    expect(await screen.findByText("2026-06-24T05:00:00 skyweaver-capture started")).toBeInTheDocument();
    await waitFor(() => expect(SkyApi.serviceDetail).toHaveBeenCalledWith("skyweaver-capture"));
  });

  it("submits first setup values", async () => {
    render(<MemoryRouter><SetupPage /></MemoryRouter>);

    expect(await screen.findByRole("heading", { name: /first setup/i })).toBeInTheDocument();
    expect(await screen.findByText("Bootstrap password is still active")).toBeInTheDocument();
    expect(screen.getByText("No hardware camera detected")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("New admin password"), { target: { value: "New-setup-secret-2026" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "New-setup-secret-2026" } });
    fireEvent.click(screen.getByRole("button", { name: /complete setup/i }));

    await waitFor(() => expect(SkyApi.completeSetup).toHaveBeenCalledWith(expect.objectContaining({
      admin_password: "New-setup-secret-2026",
      observatory_name: "Test Observatory",
      latitude: 47.1,
      longitude: 15.4,
      timezone: "Europe/Berlin",
      primary_camera_id: "cam-1",
    })));
  });

  it("renders public sky from unauthenticated latest endpoint", async () => {
    render(<PublicSky />);

    expect(await screen.findByRole("heading", { name: /sky weaver public sky/i })).toBeInTheDocument();
    expect(screen.getByText("live")).toBeInTheDocument();
    expect(screen.getByText("night")).toBeInTheDocument();
    expect(screen.getByText("1280 x 960")).toBeInTheDocument();
    expect(screen.getByAltText("Latest public all-sky capture")).toHaveAttribute("src", "/api/v1/public/latest/download?v=img-1");
    await waitFor(() => expect(SkyApi.publicLatest).toHaveBeenCalled());
  });
});
