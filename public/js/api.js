// Data access layer. Everything the pages know about the backend lives here, so
// swapping Supabase for the C++ API later only means rewriting this module.

import * as config from './config.js';

const { SUPABASE_URL, SUPABASE_ANON_KEY } = config;
// Optional: without it the page works as before, with no generated narrative.
const STORY_API_URL = (config.STORY_API_URL || '').replace(/\/$/, '');

const HEADERS = {
  apikey: SUPABASE_ANON_KEY,
  Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
};

async function request(path, options = {}) {
  const response = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    ...options,
    headers: { ...HEADERS, ...options.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.message || `Request failed (${response.status})`);
  }
  return response.json();
}

function rpc(name, args = {}, signal) {
  return request(`rpc/${name}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(args),
    signal,
  });
}

/**
 * Every facility, split by whether it can be drawn.
 * @returns {Promise<{located: object[], unlocated: object[]}>}
 */
export async function getFacilityPoints() {
  const data = await rpc('facility_points');
  return {
    located: data.points.map(([cnes, name, type, lat, lon, coordSource, susNetwork]) =>
      ({ cnes, name, type, lat, lon, coordSource, susNetwork })),
    unlocated: data.unlocated.map(([cnes, name, type, coordStatus, susNetwork]) =>
      ({ cnes, name, type, coordStatus, susNetwork })),
  };
}

/** Full record of one facility, or null if the CNES code is unknown. */
export async function getFacility(cnes) {
  const rows = await request(`infraestrutura_saude?CO_CNES=eq.${encodeURIComponent(cnes)}&select=*`);
  return rows[0] || null;
}

/** Municipal health outcomes (SINAN, SINASC, SIM) for the 39 municipalities. */
export function getMunicipalIndicators() {
  return rpc('municipal_indicators');
}

/** São Paulo city's 96 districts: SMS-SP outcomes and census factors. */
export function getDistrictIndicators() {
  return rpc('district_indicators');
}

export const hasNarrative = () => Boolean(STORY_API_URL);

/** Generated narrative for a facility and radius, from the C++ storytelling service. */
export async function getNarrative(cnes, radiusM, { lang, publicOnly }, signal) {
  const params = new URLSearchParams({ cnes, radius: radiusM, lang, public_only: publicOnly ? '1' : '0' });
  const response = await fetch(`${STORY_API_URL}/narrative?${params}`, { signal });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || `Request failed (${response.status})`);
  }
  return response.json();
}

/** Census and facility aggregates within radiusM metres of a facility. */
export function getSurroundings(cnes, radiusM, signal) {
  return rpc('facility_surroundings', { p_cnes: Number(cnes), p_radius_m: radiusM }, signal);
}
