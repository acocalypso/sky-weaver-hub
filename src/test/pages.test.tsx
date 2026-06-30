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
import RemoteUpload from "@/pages/RemoteUpload";
import Migration from "@/pages/Migration";
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
      remoteTargets: vi.fn(),
      createRemoteTarget: vi.fn(),
      patchRemoteTarget: vi.fn(),
      testRemoteTarget: vi.fn(),
      uploadJobs: vi.fn(),
      uploadJob: vi.fn(),
      queueUpload: vi.fn(),
      retryUploads: vi.fn(),
      migrationDetect: vi.fn(),
      migrationPreview: vi.fn(),
      migrationImport: vi.fn(),
      migrationJob: vi.fn(),
      rollbackMigrationJob: vi.fn(),
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
  vi.mocked(SkyApi.remoteTargets).mockResolvedValue([
    {
      id: "target-1",
      name: "Local mirror",
      type: "filesystem",
      enabled: true,
      config: { destination_path: "/tmp/skyweaver-upload" },
      created_at: "2026-06-23T12:00:00+00:00",
      updated_at: "2026-06-23T12:00:00+00:00",
    },
    {
      id: "target-rsync",
      name: "Website rsync",
      type: "rsync_ssh",
      enabled: true,
      config: { host: "allsky.example", username: "skyweaver", remote_path: "/srv/allsky", port: 22 },
      created_at: "2026-06-23T12:00:00+00:00",
      updated_at: "2026-06-23T12:00:00+00:00",
    },
    {
      id: "target-scp",
      name: "Website scp",
      type: "scp_ssh",
      enabled: true,
      config: { host: "scp.example", username: "skyweaver", remote_path: "/srv/scp", port: 22 },
      created_at: "2026-06-23T12:00:00+00:00",
      updated_at: "2026-06-23T12:00:00+00:00",
    },
  ]);
  vi.mocked(SkyApi.uploadJobs).mockResolvedValue([
    {
      id: "upload-1",
      target_id: "target-1",
      source_type: "image",
      source_id: "img-1",
      source_path: "/data/images/one.jpg",
      destination_path: "/tmp/skyweaver-upload/image/img-1/one.jpg",
      status: "completed",
      attempts: 1,
      target_name: "Local mirror",
      target_type: "filesystem",
      processing_job_id: "processing-1",
      created_at: "2026-06-23T12:00:00+00:00",
      started_at: "2026-06-23T12:00:01+00:00",
      completed_at: "2026-06-23T12:00:02+00:00",
    },
  ]);
  vi.mocked(SkyApi.uploadJob).mockResolvedValue({
    id: "upload-1",
    target_id: "target-1",
    target_name: "Local mirror",
    target_type: "filesystem",
    source_type: "image",
    source_id: "img-1",
    source_path: "/data/images/one.jpg",
    destination_path: "/tmp/skyweaver-upload/image/img-1/one.jpg",
    status: "completed",
    attempts: 1,
    processing_job_id: "processing-1",
    created_at: "2026-06-23T12:00:00+00:00",
    started_at: "2026-06-23T12:00:01+00:00",
    completed_at: "2026-06-23T12:00:02+00:00",
  });
  vi.mocked(SkyApi.createRemoteTarget).mockImplementation(async (body) => ({
    id: "target-2",
    name: body.name,
    type: body.type,
    enabled: body.enabled,
    config: body.config,
    created_at: "2026-06-23T12:00:00+00:00",
    updated_at: "2026-06-23T12:00:00+00:00",
  }));
  vi.mocked(SkyApi.patchRemoteTarget).mockImplementation(async (_id, body) => ({
    id: "target-1",
    name: body.name ?? "Local mirror",
    type: body.type ?? "filesystem",
    enabled: Boolean(body.enabled),
    config: body.config ?? { destination_path: "/tmp/skyweaver-upload" },
    created_at: "2026-06-23T12:00:00+00:00",
    updated_at: "2026-06-23T12:00:00+00:00",
  }));
  vi.mocked(SkyApi.testRemoteTarget).mockResolvedValue({ id: "target-1", status: "ready", type: "filesystem", destination_path: "/tmp/skyweaver-upload" });
  vi.mocked(SkyApi.queueUpload).mockResolvedValue({ id: "processing-1", status: "pending", upload_job_ids: ["upload-2"] });
  vi.mocked(SkyApi.retryUploads).mockResolvedValue({ status: "idle", processing_job_id: null, upload_job_ids: [] });
  vi.mocked(SkyApi.migrationDetect).mockResolvedValue([{ path: "/home/pi/allsky", exists: true }]);
  vi.mocked(SkyApi.migrationPreview).mockResolvedValue({
    path: "/home/pi/allsky",
    exists: true,
    counts: { images: 3, timelapses: 1, keograms: 1, startrails: 1 },
    settings: { observatory: { name: "Garden Allsky", latitude: 49.1 }, schedule: { sun_angle: -12 } },
    unsupported_settings: [{ path: "/home/pi/allsky/config.sh", reason: "settings_translation_not_implemented" }],
    will_delete_original: false,
    import_plan: { copy_files: true, preserve_originals: true, rollback_supported: true },
  });
  vi.mocked(SkyApi.migrationImport).mockResolvedValue({
    id: "migration-job-1",
    type: "allsky_import",
    status: "pending",
    input: { path: "/home/pi/allsky" },
    progress: 0,
    created_at: "2026-06-23T12:00:00+00:00",
  });
  vi.mocked(SkyApi.migrationJob).mockResolvedValue({
    id: "migration-job-1",
    type: "allsky_import",
    status: "completed",
    input: { path: "/home/pi/allsky" },
    output: {
      imported_images: 3,
      imported_dark_frames: 1,
      imported_products: 3,
      settings: { applied: { observatory: { name: "Garden Allsky" } } },
      import_log: [{ kind: "image", id: "img-import-1", original_path: "/home/pi/allsky/images/capture.jpg" }],
    },
    progress: 1,
    created_at: "2026-06-23T12:00:00+00:00",
  });
  vi.mocked(SkyApi.rollbackMigrationJob).mockResolvedValue({
    migration_job_id: "migration-job-1",
    deleted_images: 3,
    deleted_dark_frames: 1,
    deleted_products: 3,
    deleted_image_ids: [],
    deleted_dark_frame_ids: [],
    deleted_product_ids: [],
    deleted_files: [],
    missing_files: [],
    skipped_files: [],
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

  it("renders remote upload targets and queues latest upload", async () => {
    render(<RemoteUpload />);

    expect(await screen.findByRole("heading", { name: /remote upload/i })).toBeInTheDocument();
    expect(screen.getByText("Local mirror")).toBeInTheDocument();
    expect(screen.getAllByText(/\/tmp\/skyweaver-upload/).length).toBeGreaterThan(0);
    expect(screen.getByText(/skyweaver@allsky.example:\/srv\/allsky/)).toBeInTheDocument();
    expect(screen.getByText(/skyweaver@scp.example:\/srv\/scp/)).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /scp over ssh/i })).toBeInTheDocument();
    expect(screen.getByText("image img-1")).toBeInTheDocument();
    expect(screen.getByText(/Local mirror \(filesystem\) - attempts 1/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /details/i }));
    expect(await screen.findByText("Job detail")).toBeInTheDocument();
    expect(screen.getByText("processing-1")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: /queue latest/i })[0]);
    await waitFor(() => expect(SkyApi.queueUpload).toHaveBeenCalledWith({ source_type: "latest", target_id: undefined }));
  });

  it("renders Allsky migration preview and queues import", async () => {
    render(<Migration />);

    expect(await screen.findByRole("heading", { name: /allsky migration/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /preview/i }));
    expect(await screen.findByText("Unsupported settings")).toBeInTheDocument();
    expect(screen.getByText("Settings to apply")).toBeInTheDocument();
    expect(screen.getByText(/Garden Allsky/)).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /queue import/i }));
    await waitFor(() => expect(SkyApi.migrationImport).toHaveBeenCalledWith({ path: "/home/pi/allsky" }));
    expect(await screen.findByText("migration-job-1")).toBeInTheDocument();
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
