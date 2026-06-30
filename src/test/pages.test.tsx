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
import Modules from "@/pages/Modules";
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
      publicProducts: vi.fn(),
      modules: vi.fn(),
      registerModule: vi.fn(),
      patchModule: vi.fn(),
      moduleFlows: vi.fn(),
      patchModuleFlow: vi.fn(),
      runModuleFlow: vi.fn(),
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
  public_page: { enabled: true, iframe_enabled: true, product_days: 7 },
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
  exposure_ms: 1000,
  gain: 2,
  camera_id: "cam-1",
  download_url: "/api/v1/public/latest/download",
  metadata_url: "/api/v1/public/latest",
  thumbnail_url: "/api/v1/public/latest/thumbnail",
};

const mockPublicProducts = {
  days: 7,
  configured_days: 7,
  products: [
    {
      id: "product-1",
      type: "keogram",
      day_key: "20260623",
      status: "completed",
      created_at: "2026-06-24T05:00:00+00:00",
      metadata: { source_images: 42 },
      download_url: "/api/v1/public/products/product-1/download",
      thumbnail_url: "/api/v1/public/products/product-1/thumbnail",
    },
    {
      id: "product-2",
      type: "mini-timelapse",
      day_key: "20260623",
      status: "completed",
      created_at: "2026-06-24T05:05:00+00:00",
      metadata: { fps: 10 },
      download_url: "/api/v1/public/products/product-2/download",
      thumbnail_url: null,
    },
  ],
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
    failure_analysis: {
      severity: "warning",
      summary: "Service has warning signals that may need attention.",
      findings: [{ level: "warning", message: "systemd recorded 2 restart attempt(s)." }],
      suggested_actions: ["Check whether the service is repeatedly failing during startup or after camera access."],
    },
    unit_history: {
      restarts: 2,
      result: "success",
      exec_main_status: "0",
      recent_events: [{ label: "Entered active", value: "Wed 2026-06-24 05:00:00 UTC" }],
    },
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
    { id: "job-1", type: "single", status: "completed", request: { exposure_ms: 1000, gain: 2 }, progress: 1, created_at: "2026-06-23T22:00:00+00:00", completed_at: "2026-06-23T22:00:03+00:00", result: { image_id: "img-1" } },
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
  vi.mocked(SkyApi.publicProducts).mockResolvedValue(mockPublicProducts);
  vi.mocked(SkyApi.modules).mockResolvedValue([
    {
      id: "builtin.overlay",
      name: "Built-in overlay",
      description: "Renders configured text variables onto captured images.",
      version: "1.0.0",
      author: "Sky Weaver Hub",
      module_path: null,
      enabled: false,
      trusted: true,
      settings_schema: {},
      settings: {
        lines: [{ text: "{observatory_name}", position: "top_left" }],
        font_size: 24,
        margin: 18,
        padding: 8,
        background_color: "#00000099",
      },
      created_at: "2026-06-23T12:00:00+00:00",
      updated_at: "2026-06-23T12:00:00+00:00",
    },
  ] as any);
  vi.mocked(SkyApi.patchModule).mockImplementation(async (_id, body) => ({
    id: "builtin.overlay",
    name: "Built-in overlay",
    description: "Renders configured text variables onto captured images.",
    version: "1.0.0",
    author: "Sky Weaver Hub",
    module_path: null,
    enabled: Boolean(body.enabled),
    trusted: true,
    settings_schema: {},
    settings: body.settings ?? {},
    created_at: "2026-06-23T12:00:00+00:00",
    updated_at: "2026-06-23T12:00:00+00:00",
  }) as any);
  vi.mocked(SkyApi.registerModule).mockImplementation(async (body) => ({
    id: body.id,
    name: body.name,
    description: body.description ?? null,
    version: body.version ?? "0.1.0",
    author: body.author ?? null,
    module_path: `external:${body.id}`,
    enabled: false,
    trusted: false,
    settings_schema: body.settings_schema ?? {},
    settings: body.settings ?? {},
    created_at: "2026-06-23T12:00:00+00:00",
    updated_at: "2026-06-23T12:00:00+00:00",
  }));
  vi.mocked(SkyApi.moduleFlows).mockResolvedValue([
    {
      id: "builtin.post_capture",
      name: "Post-capture processing",
      trigger: "post_capture",
      enabled: true,
      module_order: ["builtin.overlay"],
      created_at: "2026-06-23T12:00:00+00:00",
      updated_at: "2026-06-23T12:00:00+00:00",
    },
  ]);
  vi.mocked(SkyApi.patchModuleFlow).mockImplementation(async (_id, body) => ({
    id: "builtin.post_capture",
    name: "Post-capture processing",
    trigger: "post_capture",
    enabled: body.enabled ?? true,
    module_order: ["builtin.overlay"],
    created_at: "2026-06-23T12:00:00+00:00",
    updated_at: "2026-06-23T12:00:00+00:00",
  }));
  vi.mocked(SkyApi.runModuleFlow).mockResolvedValue({
    id: "builtin.post_capture",
    trigger: "post_capture",
    status: "completed",
    enabled: true,
    modules: [{ id: "builtin.overlay", name: "Built-in overlay", enabled: true, trusted: true, status: "ready" }],
  });
});

describe("main pages", () => {
  it("renders dashboard telemetry from the API", async () => {
    render(<Dashboard />);

    expect(await screen.findByRole("heading", { name: "Test Observatory" })).toBeInTheDocument();
    expect(screen.getByText("Mock all-sky camera")).toBeInTheDocument();
    expect(screen.getByText("Recent captures")).toBeInTheDocument();
    expect(screen.getByText("single")).toBeInTheDocument();
    expect(screen.getByText(/created .*done /)).toBeInTheDocument();
    await waitFor(() => expect(SkyApi.publicLatest).toHaveBeenCalled());
  });

  it("shows latest-only captures in the dashboard hero", async () => {
    vi.mocked(SkyApi.publicLatest).mockResolvedValueOnce({
      ...mockPublicLatest,
      id: "latest-only-1",
      captured_at: "2026-06-23T22:16:30+00:00",
      mode: "day",
      exposure_ms: 10,
      gain: 1,
    });

    render(<Dashboard />);

    expect(await screen.findByText("latest only")).toBeInTheDocument();
    expect(screen.getByAltText("Latest all-sky capture")).toHaveAttribute("src", expect.stringContaining("/api/v1/public/latest/download?v=latest-only-1-"));
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
    expect(screen.getByDisplayValue("7")).toBeInTheDocument();
  });

  it("renders API key rows", async () => {
    render(<ApiKeys />);

    expect(await screen.findByRole("heading", { name: /api keys/i })).toBeInTheDocument();
    expect(screen.getByText("Mobile app")).toBeInTheDocument();
    expect(screen.getByText("swh_1234")).toBeInTheDocument();
    expect(screen.getByText("read:images")).toBeInTheDocument();
    await waitFor(() => expect(SkyApi.apiKeys).toHaveBeenCalled());
  });

  it("renders built-in overlay module controls", async () => {
    render(<Modules />);

    expect(await screen.findByRole("heading", { name: "Modules", level: 1 })).toBeInTheDocument();
    expect(screen.getAllByText("Built-in overlay")[0]).toBeInTheDocument();
    expect(screen.getByDisplayValue("{observatory_name}")).toBeInTheDocument();
    expect(screen.getByText("trusted")).toBeInTheDocument();
    await waitFor(() => expect(SkyApi.modules).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: /add line/i }));
    expect(screen.getByDisplayValue("{captured_time}")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /remove line 2/i }));
    expect(screen.queryByDisplayValue("{captured_time}")).not.toBeInTheDocument();
    expect(await screen.findByText("Post-capture processing")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /validate/i }));
    await waitFor(() => expect(SkyApi.runModuleFlow).toHaveBeenCalledWith("builtin.post_capture"));
    fireEvent.change(screen.getByPlaceholderText("external.my-module"), { target: { value: "external.test-module" } });
    fireEvent.change(screen.getByPlaceholderText("My module"), { target: { value: "Test module" } });
    fireEvent.click(screen.getByRole("button", { name: /register manifest/i }));
    await waitFor(() => expect(SkyApi.registerModule).toHaveBeenCalled());
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
    expect(screen.getByText("Failure analysis")).toBeInTheDocument();
    expect(screen.getByText("Service has warning signals that may need attention.")).toBeInTheDocument();
    expect(screen.getByText("Unit history")).toBeInTheDocument();
    expect(screen.getByText("Wed 2026-06-24 05:00:00 UTC")).toBeInTheDocument();
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
    expect(screen.getByText("Night products")).toBeInTheDocument();
    expect(screen.getByText("Keogram")).toBeInTheDocument();
    expect(screen.getByText("Mini timelapse")).toBeInTheDocument();
    expect(screen.getByText("20260623 - 42 frames")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /keogram/i })).toHaveAttribute("href", "/api/v1/public/products/product-1/download");
    expect(screen.getByTestId("public-stats")).toHaveClass("grid-cols-2");
    expect(screen.getByTestId("public-products")).toHaveClass("grid-cols-2");
    expect(screen.getByAltText("Latest public all-sky capture")).toHaveAttribute("src", "/api/v1/public/latest/download?v=img-1");
    await waitFor(() => expect(SkyApi.publicLatest).toHaveBeenCalled());
    await waitFor(() => expect(SkyApi.publicProducts).toHaveBeenCalled());
  });

  it("renders disabled public sky state", async () => {
    vi.mocked(SkyApi.publicLatest).mockRejectedValueOnce(new Error("Public page is disabled"));
    vi.mocked(SkyApi.publicProducts).mockRejectedValueOnce(new Error("Public page is disabled"));

    render(<PublicSky />);

    expect(await screen.findByText("Public page disabled")).toBeInTheDocument();
    expect(screen.getByText("disabled")).toBeInTheDocument();
    expect(screen.getByText("Disabled in Sky Weaver settings")).toBeInTheDocument();
  });
});
