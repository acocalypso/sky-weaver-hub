import SunCalc from "suncalc";

export interface TwilightTimeline {
  sunset: Date;
  civilDusk: Date;       // civil twilight end
  nauticalDusk: Date;
  astronomicalDusk: Date; // night start
  astronomicalDawn: Date; // night end
  nauticalDawn: Date;
  civilDawn: Date;
  sunrise: Date;
}

export function getTonightTimeline(lat: number, lon: number, date = new Date()): TwilightTimeline {
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

export function getSunAltitude(lat: number, lon: number, date = new Date()) {
  const pos = SunCalc.getPosition(date, lat, lon);
  return (pos.altitude * 180) / Math.PI; // degrees
}
