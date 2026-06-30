import * as SunCalc from "suncalc";

export interface TwilightTimeline {
  sunset: Date | null;
  civilDusk: Date | null;       // civil twilight end
  nauticalDusk: Date | null;
  astronomicalDusk: Date | null; // night start
  astronomicalDawn: Date | null; // night end
  nauticalDawn: Date | null;
  civilDawn: Date | null;
  sunrise: Date | null;
}

const emptyTimeline: TwilightTimeline = {
  sunset: null,
  civilDusk: null,
  nauticalDusk: null,
  astronomicalDusk: null,
  astronomicalDawn: null,
  nauticalDawn: null,
  civilDawn: null,
  sunrise: null,
};

export function isValidLatLon(lat: number, lon: number) {
  return Number.isFinite(lat) && Number.isFinite(lon) && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180;
}

function validDate(date: Date) {
  return date instanceof Date && Number.isFinite(date.getTime());
}

export function getTonightTimeline(lat: number, lon: number, date = new Date()): TwilightTimeline {
  if (!isValidLatLon(lat, lon) || !validDate(date)) return emptyTimeline;
  const t = SunCalc.getTimes(date, lat, lon);
  // suncalc keys: sunset, dusk (civil), nauticalDusk, night (astro dusk),
  //               nightEnd (astro dawn), nauticalDawn, dawn (civil), sunrise
  return {
    sunset: t.sunset,
    civilDusk: t.dusk,
    nauticalDusk: t.nauticalDusk,
    astronomicalDusk: t.night,
    astronomicalDawn: t.nightEnd,
    nauticalDawn: t.nauticalDawn,
    civilDawn: t.dawn,
    sunrise: t.sunrise,
  };
}

export function getSunAltitude(lat: number, lon: number, date = new Date()): number | null {
  if (!isValidLatLon(lat, lon) || !validDate(date)) return null;
  const pos = SunCalc.getPosition(date, lat, lon);
  const altitude = pos.altitude;
  if (!Number.isFinite(altitude) || altitude < -90.1 || altitude > 90.1) return null;
  return Math.max(-90, Math.min(90, altitude));
}
