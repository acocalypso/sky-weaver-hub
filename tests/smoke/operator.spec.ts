import { expect, type Page, type Route, test } from "@playwright/test";

const principalPayload = {
  data: {
    id: "user-admin",
    username: "admin",
    role: "admin",
    type: "user",
    scopes: ["admin"],
  },
};

const setupPayload = {
  data: {
    required: false,
    bootstrap_password_active: false,
    observatory: {
      name: "Garden",
      latitude: 56.1012,
      longitude: 16.121,
      timezone: "Europe/Berlin",
    },
    public_page: { enabled: true },
    schedule: { timezone: "Europe/Berlin", latitude: 49.1012, longitude: 10.121 },
    cameras: [{ id: "cam-1", name: "IMX290", adapter: "rpicam", enabled: true, is_primary: true }],
  },
};

const migrationPreviewPayload = {
  data: {
    path: "/home/pi/allsky",
    exists: true,
    counts: {
      images: 174,
      timelapses: 0,
      keograms: 3,
      startrails: 3,
      dark_frames: 2,
    },
    settings: {
      observatory: { name: "Garden Allsky", latitude: 49.4759, longitude: 10.9886 },
      schedule: { start_mode: "nauticalDusk", end_mode: "sunrise" },
      public_page: { enabled: true },
    },
    unsupported_settings: [
      {
        path: "/home/pi/allsky/config.sh",
        reason: "settings_translation_not_implemented",
        keys: ["CAMERA_SETTINGS", "IMG_RESIZE", "UPLOAD_IMG_DIR"],
        count: 3,
      },
    ],
    will_delete_original: false,
    import_plan: { copy_files: true, preserve_originals: true, rollback_supported: true },
  },
};

const migrationJobPayload = {
  data: {
    id: "migration-job-smoke",
    type: "allsky_import",
    status: "running",
    input: { path: "/home/pi/allsky" },
    progress: 0.35,
    created_at: "2026-07-01T08:00:00+00:00",
    started_at: "2026-07-01T08:00:01+00:00",
    output: {
      imported_images: 20,
      imported_dark_frames: 1,
      imported_products: 2,
      imported_overlay_assets: 4,
      settings: { applied: { observatory: { name: "Garden Allsky" } } },
      import_log: [
        {
          kind: "image",
          id: "img-imported-1",
          original_path: "/home/pi/allsky/images/20260630/image-001.jpg",
        },
        {
          kind: "keogram",
          id: "keogram-imported-1",
          original_path: "/home/pi/allsky/images/20260630/keogram.jpg",
        },
      ],
    },
  },
};

const remoteTargetsPayload = {
  data: [
    {
      id: "target-local",
      name: "Local mirror",
      type: "filesystem",
      enabled: true,
      config: { destination_path: "/mnt/allsky-upload" },
      created_at: "2026-07-01T08:00:00+00:00",
      updated_at: "2026-07-01T08:00:00+00:00",
    },
    {
      id: "target-sftp",
      name: "Observatory SFTP",
      type: "sftp_ssh",
      enabled: true,
      config: {
        host: "storage.local",
        username: "skyweaver",
        remote_path: "/srv/allsky",
        port: 22,
      },
      created_at: "2026-07-01T08:00:00+00:00",
      updated_at: "2026-07-01T08:00:00+00:00",
    },
  ],
};

const uploadJobsPayload = {
  data: [
    {
      id: "upload-job-1",
      target_id: "target-local",
      target_name: "Local mirror",
      target_type: "filesystem",
      target_enabled: true,
      source_type: "image",
      source_id: "img-1",
      source_path: "/var/lib/skyweaver/images/20260701/image.jpg",
      destination_path: "/mnt/allsky-upload/images/20260701/image.jpg",
      status: "completed",
      attempts: 1,
      last_error: null,
      processing_job_id: "processing-upload-1",
      created_at: "2026-07-01T08:00:00+00:00",
      started_at: "2026-07-01T08:00:01+00:00",
      completed_at: "2026-07-01T08:00:02+00:00",
    },
    {
      id: "upload-job-2",
      target_id: "target-sftp",
      target_name: "Observatory SFTP",
      target_type: "sftp_ssh",
      target_enabled: true,
      source_type: "latest",
      source_id: "latest",
      source_path: "/var/lib/skyweaver/latest/latest.jpg",
      destination_path: "/srv/allsky/latest.jpg",
      status: "failed",
      attempts: 2,
      last_error: "Connection refused",
      processing_job_id: "processing-upload-2",
      created_at: "2026-07-01T08:01:00+00:00",
      started_at: "2026-07-01T08:01:01+00:00",
      completed_at: "2026-07-01T08:01:03+00:00",
    },
  ],
};

test.describe("operator page smoke", () => {
  test.beforeEach(async ({ page }) => {
    await mockProtectedSession(page);
  });

  test("renders Allsky migration preview and queued import state", async ({ page }) => {
    let releasePreview: () => void = () => undefined;
    const previewHold = new Promise<void>((resolve) => {
      releasePreview = resolve;
    });
    await page.route("**/api/v1/migration/allsky/preview", async (route) => {
      await previewHold;
      await fulfillJson(route, migrationPreviewPayload);
    });
    await page.route("**/api/v1/migration/allsky/import", async (route) => {
      expect(route.request().method()).toBe("POST");
      await fulfillJson(route, migrationJobPayload);
    });
    await page.route("**/api/v1/migration/jobs/migration-job-smoke", async (route) => {
      await fulfillJson(route, migrationJobPayload);
    });

    await page.goto("/migration");

    await expect(page.getByRole("heading", { name: /allsky migration/i })).toBeVisible();
    await page.getByRole("button", { name: /^preview$/i }).click();
    await expect(page.getByText(/Scanning the Allsky tree/i)).toBeVisible();
    releasePreview();
    await expect(page.getByText("Unsupported settings")).toBeVisible();
    await expect(page.getByText("Settings to apply")).toBeVisible();
    await expect(page.getByText(/Garden Allsky/)).toBeVisible();
    await expect(page.getByText("dark_frames")).toBeVisible();

    await page.getByRole("button", { name: /queue import/i }).click();

    await expect(page.getByText("Import job")).toBeVisible();
    await expect(page.getByText("migration-job-smoke")).toBeVisible();
    await expect(page.getByText("35%")).toBeVisible();
    await expect(page.getByText("image: 1 - keogram: 1")).toBeVisible();
  });

  test("renders remote upload targets, job details, and queue actions", async ({ page }) => {
    let queueLatestRequested = false;

    await page.route("**/api/v1/remote-targets", async (route) => {
      await fulfillJson(route, remoteTargetsPayload);
    });
    await page.route("**/api/v1/uploads/jobs", async (route) => {
      await fulfillJson(route, uploadJobsPayload);
    });
    await page.route("**/api/v1/uploads/jobs/upload-job-2", async (route) => {
      await fulfillJson(route, { data: uploadJobsPayload.data[1] });
    });
    await page.route("**/api/v1/uploads/queue", async (route) => {
      queueLatestRequested = true;
      expect(route.request().method()).toBe("POST");
      await fulfillJson(route, {
        data: { id: "processing-upload-queued", status: "pending", upload_job_ids: ["upload-job-queued"] },
      });
    });
    await page.route("**/api/v1/uploads/retry", async (route) => {
      expect(route.request().method()).toBe("POST");
      await fulfillJson(route, {
        data: { status: "queued", processing_job_id: "processing-retry-1", upload_job_ids: ["upload-job-2"] },
      });
    });
    await page.route("**/api/v1/remote-targets/target-sftp/test", async (route) => {
      await fulfillJson(route, {
        data: { id: "target-sftp", status: "ok", type: "sftp_ssh", destination_path: "/srv/allsky" },
      });
    });

    await page.goto("/remote-upload");

    await expect(page.getByRole("heading", { name: /remote upload/i })).toBeVisible();
    await expect(page.getByTestId("remote-summary-targets")).toContainText("2");
    await expect(page.getByTestId("remote-summary-enabled")).toContainText("2");
    await expect(page.getByTestId("remote-summary-failed-jobs")).toContainText("1");
    await expect(page.getByText("Local mirror", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Observatory SFTP", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Connection refused")).toBeVisible();

    await page.getByRole("button", { name: /details/i }).nth(1).click();
    await expect(page.getByText("Job detail")).toBeVisible();
    await expect(page.getByText("processing-upload-2")).toBeVisible();

    await page.getByRole("button", { name: /^queue latest$/i }).first().click();
    await expect.poll(() => queueLatestRequested).toBe(true);
  });
});

async function mockProtectedSession(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("skyweaver_token", "smoke-token");
  });
  await page.route("**/api/v1/auth/me", async (route) => {
    await fulfillJson(route, principalPayload);
  });
  await page.route("**/api/v1/setup/status", async (route) => {
    await fulfillJson(route, setupPayload);
  });
}

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}
