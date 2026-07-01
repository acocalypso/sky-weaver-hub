import { expect, type Page, test } from "@playwright/test";

const latestPayload = {
  data: {
    id: "img-smoke-1",
    captured_at: "2026-06-30T22:15:00+00:00",
    day_key: "20260630",
    mode: "night",
    format: "jpg",
    width: 1920,
    height: 1080,
    size_bytes: 734_003,
    exposure_ms: 1000,
    gain: 2,
    camera_id: "cam-1",
    download_url: "/api/v1/public/latest/download",
    metadata_url: "/api/v1/public/latest",
    thumbnail_url: "/api/v1/public/latest/thumbnail",
  },
};

const productsPayload = {
  data: {
    days: 7,
    configured_days: 7,
    products: [
      {
        id: "keogram-smoke",
        type: "keogram",
        day_key: "20260630",
        status: "completed",
        created_at: "2026-07-01T04:00:00+00:00",
        metadata: { source_images: 120 },
        download_url: "/api/v1/public/products/keogram-smoke/download",
        thumbnail_url: "/api/v1/public/products/keogram-smoke/thumbnail",
      },
      {
        id: "startrail-smoke",
        type: "startrail",
        day_key: "20260630",
        status: "completed",
        created_at: "2026-07-01T04:05:00+00:00",
        metadata: { source_images: 120 },
        download_url: "/api/v1/public/products/startrail-smoke/download",
        thumbnail_url: null,
      },
      {
        id: "timelapse-smoke",
        type: "timelapse",
        day_key: "20260630",
        status: "completed",
        created_at: "2026-07-01T04:10:00+00:00",
        metadata: { source_images: 120, fps: 24 },
        download_url: "/api/v1/public/products/timelapse-smoke/download",
        thumbnail_url: "/api/v1/public/products/timelapse-smoke/thumbnail",
      },
      {
        id: "mini-timelapse-smoke",
        type: "mini_timelapse",
        day_key: "20260630",
        status: "completed",
        created_at: "2026-07-01T04:15:00+00:00",
        metadata: { used_images: 30, fps: 10 },
        download_url: "/api/v1/public/products/mini-timelapse-smoke/download",
        thumbnail_url: null,
      },
    ],
  },
};

test.describe("public page smoke", () => {
  test("renders enabled latest image and product archive without admin auth", async ({ page }) => {
    await mockPublicApi(page);
    await page.goto("/public");

    await expect(page.getByRole("heading", { name: /sky weaver public sky/i })).toBeVisible();
    await expect(page.getByText("live")).toBeVisible();
    await expect(page.getByAltText("Latest public all-sky capture")).toHaveAttribute("src", /\/api\/v1\/public\/latest\/download\?v=img-smoke-1/);
    await expect(page.getByText("1920 x 1080")).toBeVisible();
    await expect(page.getByText("Night products")).toBeVisible();
    await expect(page.getByRole("link", { name: /^Keogram/i })).toHaveAttribute("href", /\/api\/v1\/public\/products\/keogram-smoke\/download$/);
    await expect(page.getByRole("link", { name: /^Startrail/i })).toHaveAttribute("href", /\/api\/v1\/public\/products\/startrail-smoke\/download$/);
    await expect(page.getByRole("link", { name: /^Timelapse/i })).toHaveAttribute("href", /\/api\/v1\/public\/products\/timelapse-smoke\/download$/);
    await expect(page.getByRole("link", { name: /^Mini timelapse/i })).toHaveAttribute("href", /\/api\/v1\/public\/products\/mini-timelapse-smoke\/download$/);
  });

  test("keeps public metadata and product controls usable on mobile", async ({ page, isMobile }) => {
    test.skip(!isMobile, "mobile layout smoke runs only in the mobile project");

    await mockPublicApi(page);
    await page.goto("/public");

    const stats = page.getByTestId("public-stats");
    const products = page.getByTestId("public-products");
    await expect(stats).toBeVisible();
    await expect(products).toBeVisible();

    const statsBox = await stats.boundingBox();
    const productsBox = await products.boundingBox();
    expect(statsBox?.width).toBeLessThanOrEqual(400);
    expect(productsBox?.width).toBeLessThanOrEqual(400);
    await expect(page.getByRole("link", { name: /^Mini timelapse/i })).toBeVisible();
  });

  test("renders disabled state when public API is disabled", async ({ page }) => {
    await page.route("**/api/v1/public/**", async (route) => {
      await route.fulfill({
        status: 403,
        contentType: "application/json",
        body: JSON.stringify({ error: { message: "Public page is disabled" } }),
      });
    });

    await page.goto("/public");

    await expect(page.getByText("Public page disabled")).toBeVisible();
    await expect(page.getByText("Disabled in Sky Weaver settings")).toBeVisible();
  });
});

async function mockPublicApi(page: Page) {
  await page.route("**/api/v1/public/latest", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(latestPayload) });
  });
  await page.route("**/api/v1/public/products", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(productsPayload) });
  });
  await page.route("**/api/v1/public/**/*.jpg", async (route) => {
    await route.fulfill({ status: 200, contentType: "image/jpeg", body: tinyJpeg });
  });
  await page.route("**/api/v1/public/**/thumbnail**", async (route) => {
    await route.fulfill({ status: 200, contentType: "image/jpeg", body: tinyJpeg });
  });
  await page.route("**/api/v1/public/**/download**", async (route) => {
    await route.fulfill({ status: 200, contentType: "image/jpeg", body: tinyJpeg });
  });
}

const tinyJpeg = Buffer.from(
  "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAH/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAEFAqf/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/ASP/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAECAQE/ASP/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAY/As//xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/IV//2gAMAwEAAgADAAAAEP/EABQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQMBAT8QH//EABQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQIBAT8QH//EABQQAQAAAAAAAAAAAAAAAAAAABD/2gAIAQEAAT8QH//Z",
  "base64",
);
