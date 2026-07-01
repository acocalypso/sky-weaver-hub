import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "@/App";
import { SkyApi } from "@/lib/api";

vi.mock("sonner", () => ({
  Toaster: () => null,
  toast: {
    error: vi.fn(),
    message: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock("@/pages/PublicSky", () => ({ default: () => <h1>Public route</h1> }));
vi.mock("@/pages/Deployment", () => ({ default: () => <h1>Deployment route</h1> }));
vi.mock("@/pages/Setup", () => ({ default: () => <h1>First setup route</h1> }));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    SkyApi: {
      me: vi.fn(),
      setupStatus: vi.fn(),
      publicLatest: vi.fn(),
      publicProducts: vi.fn(),
      detectCameras: vi.fn(),
    },
  };
});

const principal = {
  subject: "admin",
  username: "admin",
  role: "admin",
  scopes: ["admin"],
  key_id: null,
};

const setupComplete = {
  required: false,
  bootstrap_password_active: false,
  observatory: { name: "Garden", latitude: 49.1, longitude: 10.1, timezone: "Europe/Berlin" },
  public_page: { enabled: true },
  schedule: { timezone: "Europe/Berlin", latitude: 49.1, longitude: 10.1 },
  cameras: [{ id: "cam-1", name: "IMX290", adapter: "rpicam", enabled: true, is_primary: true }],
};

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  window.history.pushState({}, "", "/");
  vi.mocked(SkyApi.me).mockResolvedValue(principal as any);
  vi.mocked(SkyApi.setupStatus).mockResolvedValue(setupComplete as any);
  vi.mocked(SkyApi.detectCameras).mockResolvedValue([]);
  vi.mocked(SkyApi.publicLatest).mockResolvedValue({
    id: "img-1",
    captured_at: "2026-06-23T22:15:00+00:00",
    day_key: "20260623",
    mode: "night",
    format: "jpg",
    width: 1280,
    height: 960,
    size_bytes: 12345,
    download_url: "/api/v1/public/latest/download",
    metadata_url: "/api/v1/public/latest",
    thumbnail_url: "/api/v1/public/latest/thumbnail",
  } as any);
  vi.mocked(SkyApi.publicProducts).mockResolvedValue({ days: 7, configured_days: 7, products: [] });
});

function renderAt(path: string, authenticated = false) {
  window.history.pushState({}, "", path);
  if (authenticated) localStorage.setItem("skyweaver_token", "test-token");
  return render(<App />);
}

describe("app route smoke tests", () => {
  it("renders the public route without authentication", async () => {
    renderAt("/public");

    expect(await screen.findByRole("heading", { name: /public route/i })).toBeInTheDocument();
    expect(SkyApi.me).not.toHaveBeenCalled();
  });

  it("redirects protected routes to sign in when unauthenticated", async () => {
    renderAt("/deployment");

    expect(await screen.findByRole("heading", { name: "Sky Weaver Hub" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/auth");
  });

  it("renders a protected route when authenticated and setup is complete", async () => {
    renderAt("/deployment", true);

    expect(await screen.findByRole("heading", { name: /deployment route/i })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/deployment");
  });

  it("redirects protected routes to first setup when setup is required", async () => {
    vi.mocked(SkyApi.setupStatus).mockResolvedValue({ ...setupComplete, required: true, bootstrap_password_active: true } as any);

    renderAt("/deployment", true);

    expect(await screen.findByRole("heading", { name: /first setup route/i })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/setup");
  });
});
