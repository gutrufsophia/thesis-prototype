// Facility page: the full record of one facility, plus census and health-network
// indicators for an adjustable radius around it.

import { getFacility, getSurroundings } from './api.js';
import { barList, el, section, statTiles } from './charts.js';
import { facilityHeader, renderFacility } from './facility-view.js';
import {
  COORD_STATUS, TYPE_GROUPS, facilityName, formatCount, formatDistance, formatNumber, formatPercent,
  positionNote, typeInfo,
} from './fields.js';

const REQUEST_DELAY_MS = 300;
const NEAREST_SHOWN = 10;
const NO_DATA_COLOR = '#e1e0d9';
// Sequential blue ramp, light to dark: more of the indicator is darker
const RAMP = ['#cde2fb', '#9ec5f4', '#5598e7', '#256abf', '#0d366b'];

// `breaks` are the lower bounds of ramp steps 2..5
const INDICATORS = [
  {
    id: 'no_sewage',
    label: 'Households not on the sewage network',
    value: (p) => (p.sewage_pct === null ? null : 100 - p.sewage_pct),
    breaks: [5, 15, 30, 50],
    format: formatPercent,
  },
  {
    id: 'no_garbage',
    label: 'Households without garbage collection',
    value: (p) => (p.garbage_pct === null ? null : 100 - p.garbage_pct),
    breaks: [1, 3, 10, 25],
    format: formatPercent,
  },
  {
    id: 'crowding',
    label: 'Residents per household',
    value: (p) => (p.households ? p.residents_per_household : null),
    breaks: [2.5, 2.8, 3.1, 3.4],
    format: (value) => formatNumber(value, 1),
  },
];

const cnes = new URLSearchParams(location.search).get('cnes');
const dom = {
  root: document.getElementById('facility-root'),
  surroundings: document.getElementById('surroundings'),
  body: document.getElementById('surroundings-body'),
  locationLine: document.getElementById('location-line'),
  radius: document.getElementById('radius'),
  radiusValue: document.getElementById('radius-value'),
  indicator: document.getElementById('indicator'),
  tiles: document.getElementById('tiles'),
  mapLegend: document.getElementById('map-legend'),
  comparisons: document.getElementById('comparisons'),
  nearbyTypes: document.getElementById('nearby-types'),
  nearbyList: document.getElementById('nearby-list'),
};

let facility = null;
let surroundings = null;
let map = null;
let layers = null;
let pendingRequest = null;
let requestTimer = null;

function rampColor(indicator, properties) {
  const value = indicator.value(properties);
  if (value === null || value === undefined) return NO_DATA_COLOR;
  let step = 0;
  while (step < indicator.breaks.length && value >= indicator.breaks[step]) step += 1;
  return RAMP[step];
}

function currentIndicator() {
  return INDICATORS.find((indicator) => indicator.id === dom.indicator.value);
}

// Created on the first response, which carries the facility's coordinates
function setupMap() {
  const position = [surroundings.facility.lat, surroundings.facility.lon];
  map = L.map('mini-map', { preferCanvas: true, scrollWheelZoom: false }).setView(position, 14);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  }).addTo(map);
  layers = {
    tracts: L.geoJSON(null).addTo(map),
    circle: L.circle(position, {
      radius: Number(dom.radius.value), color: '#0b0b0b', weight: 2, fill: false, interactive: false,
    }).addTo(map),
    nearby: L.layerGroup().addTo(map),
  };
  L.circleMarker(position, {
    radius: 8, color: '#fcfcfb', weight: 2, fillColor: '#0b0b0b', fillOpacity: 1,
  }).bindTooltip(facility.name).addTo(map);
}

function tractTooltip(properties) {
  const lines = [`Census tract ${properties.cd_setor}`];
  if (!properties.households) {
    lines.push('No occupied households');
  } else {
    lines.push(
      `${formatCount(properties.population)} residents · ${formatCount(properties.households)} households`,
      ...INDICATORS.map((indicator) => `${indicator.label}: ${indicator.format(indicator.value(properties))}`));
  }
  if (properties.share_inside < 1) lines.push(`${formatPercent(properties.share_inside * 100)} of its area is inside the radius`);
  return el('div', { class: 'tract-tooltip' }, lines.map((line, index) =>
    el(index === 0 ? 'strong' : 'span', { text: line })));
}

function drawTracts() {
  const indicator = currentIndicator();
  layers.tracts.clearLayers();
  L.geoJSON(surroundings.tracts, {
    style: (feature) => ({
      fillColor: rampColor(indicator, feature.properties),
      fillOpacity: 0.75,
      color: '#fcfcfb',
      weight: 1,
    }),
    onEachFeature: (feature, layer) => {
      layer.bindTooltip(() => tractTooltip(feature.properties), { sticky: true });
      layer.on('mouseover', () => layer.setStyle({ color: '#0b0b0b', weight: 2 }));
      layer.on('mouseout', () => layer.setStyle({ color: '#fcfcfb', weight: 1 }));
    },
  }).addTo(layers.tracts);

  const bounds = [`under ${indicator.format(indicator.breaks[0])}`];
  indicator.breaks.forEach((lower, index) => {
    const upper = indicator.breaks[index + 1];
    bounds.push(upper === undefined ? `${indicator.format(lower)} or more` : `${indicator.format(lower)} to ${indicator.format(upper)}`);
  });
  dom.mapLegend.replaceChildren(
    ...bounds.map((text, index) => el('span', { class: 'ramp-step' },
      el('span', { class: 'swatch', style: { background: RAMP[index] } }), text)),
    el('span', { class: 'ramp-step' },
      el('span', { class: 'swatch', style: { background: NO_DATA_COLOR } }), 'no households'));
}

function drawNearby() {
  layers.nearby.clearLayers();
  for (const other of surroundings.facilities) {
    const info = typeInfo(other.type);
    L.circleMarker([other.lat, other.lon], {
      radius: 5, color: '#fcfcfb', weight: 2, fillColor: info.color, fillOpacity: 1,
    })
      .bindTooltip(`${other.name} · ${info.label} · ${formatDistance(other.distance_m)}`)
      .on('click', () => { location.href = `facility.html?cnes=${other.cnes}`; })
      .addTo(layers.nearby);
  }
}

function renderTiles() {
  const { census, facilities, area_km2: area } = surroundings;
  const radius = census.radius;
  const beds = facilities.reduce((sum, other) => sum + (other.beds || 0), 0) + (facility.beds || 0);
  const physicians = facilities.reduce((sum, other) => sum + (other.physicians || 0), 0) + (facility.physicians || 0);
  const per10k = (count) => (radius.population ? formatNumber((count / radius.population) * 10000, 1) : '–');
  dom.tiles.replaceChildren(statTiles([
    { label: 'Residents (est.)', value: formatCount(radius.population), note: `${formatCount(radius.tracts)} census tracts` },
    { label: 'Households (est.)', value: formatCount(radius.households) },
    { label: 'Residents per km²', value: formatCount(Math.round((radius.population || 0) / area)) },
    { label: 'Other facilities', value: formatCount(facilities.length), note: 'within the radius' },
    { label: 'Beds', value: formatCount(beds), note: `${per10k(beds)} per 10,000 residents` },
    { label: 'Care-team physicians', value: formatCount(physicians), note: `${per10k(physicians)} per 10,000 residents` },
  ]));
}

function renderComparisons() {
  const { census, location: place } = surroundings;
  const scopes = [
    { label: `Within ${formatDistance(surroundings.radius_m)}`, data: census.radius },
    { label: place?.municipality || 'Municipality', data: census.municipality, muted: true },
    { label: 'Metropolitan region', data: census.region, muted: true },
  ].filter((scope) => scope.data);

  const chart = (title, pick, options) => section(title, barList(
    scopes.map((scope) => ({ label: scope.label, value: pick(scope.data), muted: scope.muted })), options));
  const lacking = (percent) => (percent === null ? null : Math.round((100 - percent) * 10) / 10);

  dom.comparisons.replaceChildren(
    el('h3', { class: 'card-title', text: 'Compared with its context' }),
    chart('Households not on the sewage network', (d) => lacking(d.sewage_pct), { digits: 1, suffix: '%' }),
    chart('Households without garbage collection', (d) => lacking(d.garbage_pct), { digits: 1, suffix: '%' }),
    chart('Residents per household', (d) => d.residents_per_household, { digits: 2 }));
}

function renderNearby() {
  const { facilities } = surroundings;
  const counts = new Map();
  for (const other of facilities) counts.set(other.type, (counts.get(other.type) || 0) + 1);
  const byType = [...counts.entries()]
    .map(([type, value]) => ({ label: typeInfo(type).label, value, color: typeInfo(type).color }))
    .sort((a, b) => b.value - a.value);

  dom.nearbyTypes.replaceChildren(section('Other facilities by type', byType.length ? barList(byType) : null, {
    hint: byType.length ? 'Bar colour is the facility category used on the map.' : null,
    emptyText: 'No other facility within this radius.',
  }));
  if (byType.length) {
    const used = new Set(facilities.map((other) => typeInfo(other.type).group));
    dom.nearbyTypes.append(el('div', { class: 'ramp-legend' }, TYPE_GROUPS
      .filter((group) => used.has(group.id))
      .map((group) => el('span', { class: 'ramp-step' },
        el('span', { class: 'dot', style: { background: group.color } }), group.label))));
  }

  const nearest = facilities.slice(0, NEAREST_SHOWN);
  const table = nearest.length ? el('table', { class: 'table' },
    el('thead', {}, el('tr', {},
      el('th', { text: 'Facility' }), el('th', { text: 'Type' }),
      el('th', { class: 'num', text: 'Distance' }), el('th', { class: 'num', text: 'Beds' }))),
    el('tbody', {}, nearest.map((other) => el('tr', {},
      el('td', {}, el('a', { href: `facility.html?cnes=${other.cnes}`, text: other.name })),
      el('td', { text: typeInfo(other.type).label }),
      el('td', { class: 'num', text: formatDistance(other.distance_m) }),
      el('td', { class: 'num', text: formatCount(other.beds) }))))) : null;
  dom.nearbyList.replaceChildren(section('Nearest facilities', table, {
    hint: facilities.length > NEAREST_SHOWN ? `Closest ${NEAREST_SHOWN} of ${formatCount(facilities.length)}, straight-line distance.` : 'Straight-line distance.',
    emptyText: 'No other facility within this radius.',
  }));
}

function renderSurroundings() {
  const place = surroundings.location;
  dom.locationLine.textContent = place
    ? `Located in ${place.district && place.district !== place.municipality ? `${place.district}, ` : ''}${place.municipality} · census tract ${place.tract}`
    : '';
  layers.circle.setRadius(surroundings.radius_m);
  map.fitBounds(layers.circle.getBounds(), { padding: [16, 16] });
  drawTracts();
  drawNearby();
  renderTiles();
  renderComparisons();
  renderNearby();
}

async function loadSurroundings() {
  pendingRequest?.abort();
  const controller = new AbortController();
  pendingRequest = controller;
  dom.body.classList.add('is-loading');
  try {
    const data = await getSurroundings(cnes, Number(dom.radius.value), controller.signal);
    if (controller.signal.aborted) return;
    surroundings = data;
    if (!map) setupMap();
    renderSurroundings();
  } catch (error) {
    if (error.name === 'AbortError') return;
    dom.tiles.replaceChildren(el('p', { class: 'notice is-error', text: `Could not load the surroundings: ${error.message}` }));
  } finally {
    if (pendingRequest === controller) dom.body.classList.remove('is-loading');
  }
}

function onRadiusInput() {
  const radius = Number(dom.radius.value);
  dom.radiusValue.textContent = formatDistance(radius);
  layers?.circle.setRadius(radius);
  clearTimeout(requestTimer);
  requestTimer = setTimeout(loadSurroundings, REQUEST_DELAY_MS);
}

async function init() {
  if (!cnes) {
    dom.root.replaceChildren(el('p', { class: 'notice', text: 'No facility selected. Go back to the map and pick one.' }));
    return;
  }
  document.getElementById('back').href = `index.html?cnes=${encodeURIComponent(cnes)}`;

  let row;
  try {
    row = await getFacility(cnes);
  } catch (error) {
    dom.root.replaceChildren(el('p', { class: 'notice is-error', text: `Could not load this facility: ${error.message}` }));
    return;
  }
  if (!row) {
    dom.root.replaceChildren(el('p', { class: 'notice', text: `No facility with CNES code ${cnes}.` }));
    return;
  }

  document.title = `${facilityName(row)} · CulturaEduca Health Layer`;
  dom.root.replaceChildren(facilityHeader(row, 'h1'), renderFacility(row));

  if (!row.coord) {
    dom.root.append(el('p', { class: 'notice', text:
      `The surroundings cannot be analysed. ${COORD_STATUS[row.coord_status] || 'This facility has no usable coordinates.'}` }));
    return;
  }
  facility = {
    name: facilityName(row),
    beds: Number(row.LEITOS_EXISTENTES) || 0,
    physicians: Number(row.total_medicos) || 0,
  };

  // An uncertain position only supports radii clearly larger than its uncertainty
  const precision = Number(row.coord_precision_m) || 0;
  const step = Number(dom.radius.step);
  const minRadius = Math.max(Number(dom.radius.min), Math.ceil((2 * precision) / step) * step);
  dom.radius.min = minRadius;
  dom.radius.value = Math.max(Number(dom.radius.value), minRadius);
  dom.radiusValue.textContent = formatDistance(Number(dom.radius.value));
  const note = positionNote(row);
  if (note) {
    const limit = minRadius > step
      ? ` Radii below ${formatDistance(minRadius)} are disabled, since they would be smaller than twice this uncertainty.`
      : '';
    dom.locationLine.after(el('p', { class: 'notice', text: note + limit }));
  }

  dom.indicator.replaceChildren(...INDICATORS.map((indicator) =>
    el('option', { value: indicator.id, text: indicator.label })));
  dom.surroundings.hidden = false;
  dom.radius.addEventListener('input', onRadiusInput);
  dom.indicator.addEventListener('change', () => surroundings && drawTracts());
  loadSurroundings();
}

init();
