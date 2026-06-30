import { describe, expect, it } from "vitest";

import { getSunAltitude, isValidLatLon } from "@/lib/sun";

describe("sun helpers", () => {
  it("returns a valid sun altitude for the observatory coordinates", () => {
    const altitude = getSunAltitude(49.1012, 10.1210, new Date("2026-06-30T05:49:17.290Z"));

    expect(altitude).not.toBeNull();
    expect(altitude).toBeGreaterThanOrEqual(-90);
    expect(altitude).toBeLessThanOrEqual(90);
  });

  it("rejects invalid coordinate ranges", () => {
    expect(isValidLatLon(91, 10.1210)).toBe(false);
    expect(getSunAltitude(49.1012, 181)).toBeNull();
  });
});
