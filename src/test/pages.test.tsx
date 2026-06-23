import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Dashboard from "@/pages/Dashboard";
import Gallery from "@/pages/Gallery";
import SettingsPage from "@/pages/Settings";
import ApiKeys from "@/pages/ApiKeys";
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
      schedulePreview: vi.fn(),
      captureJobs: vi.fn(),
      apiKeys: vi.fn(),
      patchSettings: vi.fn(),
      createApiKey: vi.fn(),
      patchApiKey: vi.fn(),
      deleteApiKey: vi.fn(),
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
});
