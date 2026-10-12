// Data access layer. Everything the pages know about the backend lives here, so
// swapping Supabase for the C++ API later only means rewriting this module.

import { SUPABASE_URL, SUPABASE_ANON_KEY } from './config.js';

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
    located: data.points.map(([cnes, name, type, lat, lon, coordSource]) => ({ cnes, name, type, lat, lon, coordSource })),
    unlocated: data.unlocated.map(([cnes, name, type, coordStatus]) => ({ cnes, name, type, coordStatus })),
  };
}

/** Full record of one facility, or null if the CNES code is unknown. */
export async function getFacility(cnes) {
  const rows = await request(`infraestrutura_saude?CO_CNES=eq.${encodeURIComponent(cnes)}&select=*`);
  return rows[0] || null;
}

/** Census and facility aggregates within radiusM metres of a facility. */
export function getSurroundings(cnes, radiusM, signal) {
  return rpc('facility_surroundings', { p_cnes: Number(cnes), p_radius_m: radiusM }, signal);
}
