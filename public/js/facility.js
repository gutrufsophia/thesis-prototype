// Facility page: the full record of one facility, plus census and health-network
// indicators for an adjustable radius around it.

import { getFacility, getNarrative, getSurroundings, hasNarrative } from './api.js';
import { barList, el, section, statTiles } from './charts.js';
import { facilityHeader, renderFacility } from './facility-view.js';
import { renderNarrative, renderNarrativeState } from './narrative.js';
import { renderTerritory } from './territory.js';
import {
  TYPE_GROUPS, coordStatusNote, facilityName, formatCount, formatDistance, formatNumber, formatPercent,
  positionNote, typeInfo,
} from './fields.js';
import { applyStaticTranslations, getPref, lang, pick, setPref, t } from './i18n.js';

const REQUEST_DELAY_MS = 300;
const NEAREST_SHOWN = 10;
const PUBLIC_ONLY_PREF = 'publicOnly';
const NO_DATA_COLOR = '#e1e0d9';
// Sequential blue ramp, light to dark: more of the indicator is darker
const RAMP = ['#cde2fb', '#9ec5f4', '#5598e7', '#256abf', '#0d366b'];

// `breaks` are the lower bounds of ramp steps 2..5
const INDICATORS = [
  {
    id: 'no_sewage',
    label: t('ind.noSewage'),
    value: (p) => (p.sewage_pct === null ? null : 100 - p.sewage_pct),
    breaks: [5, 15, 30, 50],
    format: formatPercent,
  },
  {
    id: 'precarious',
    label: t('ind.precarious'),
    value: (p) => p.precarious_pct,
    breaks: [2, 5, 15, 30],
    format: formatPercent,
  },
  {
    id: 'no_garbage',
    label: t('ind.noGarbage'),
    value: (p) => (p.garbage_pct === null ? null : 100 - p.garbage_pct),
    breaks: [1, 3, 10, 25],
    format: formatPercent,
  },
  {
    id: 'crowding',
    label: t('ind.crowding'),
    value: (p) => (p.households ? p.residents_per_household : null),
    breaks: [2.5, 2.8, 3.1, 3.4],
    format: (value) => formatNumber(value, 1),
  },
  {
    id: 'primary_distance',
    label: t('ind.primaryDistance'),
    value: (p) => p.dist_primary_m,
    breaks: [500, 1000, 2000, 4000],
    format: formatDistance,
  },
];

applyStaticTranslations();
document.title = t('page.title');

const cnes = new URLSearchParams(location.search).get('cnes');
const dom = {
  root: document.getElementById('facility-root'),
  surroundings: document.getElementById('surroundings'),
  body: document.getElementById('surroundings-body'),
  locationLine: document.getElementById('location-line'),
  radius: document.getElementById('radius'),
  radiusValue: document.getElementById('radius-value'),
  publicOnly: document.getElementById('public-only'),
  indicator: document.getElementById('indicator'),
  tiles: document.getElementById('tiles'),
  mapLegend: document.getElementById('map-legend'),
  nearbyTypes: document.getElementById('nearby-types'),
  nearbyList: document.getElementById('nearby-list'),
  narrative: document.getElementById('narrative'),
};

let facility = null;
let surroundings = null;
let map = null;
let layers = null;
let pendingRequest = null;
let pendingNarrative = null;
let requestTimer = null;
// Private facilities without a SUS link are shown unless the user asks for the public network only
let showPrivate = !getPref(PUBLIC_ONLY_PREF);

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

/** Nearby facilities the page counts: all of them, or only the public network on request. */
function countedFacilities() {
  return surroundings.facilities.filter((other) => other.sus_network || showPrivate);
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
  const lines = [t('tract.name', { code: properties.cd_setor })];
  if (!properties.households) {
    lines.push(t('tract.empty'));
  } else {
    lines.push(
      t('tract.people', { residents: formatCount(properties.population), households: formatCount(properties.households) }),
      ...INDICATORS.map((indicator) => `${indicator.label}: ${indicator.format(indicator.value(properties))}`));
  }
  if (properties.share_inside < 1) lines.push(t('tract.share', { share: formatPercent(properties.share_inside * 100) }));
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

  const bounds = [t('ramp.under', { value: indicator.format(indicator.breaks[0]) })];
  indicator.breaks.forEach((lower, index) => {
    const upper = indicator.breaks[index + 1];
    bounds.push(upper === undefined
      ? t('ramp.over', { value: indicator.format(lower) })
      : t('ramp.range', { low: indicator.format(lower), high: indicator.format(upper) }));
  });
  dom.mapLegend.replaceChildren(
    ...bounds.map((text, index) => el('span', { class: 'ramp-step' },
      el('span', { class: 'swatch', style: { background: RAMP[index] } }), text)),
    el('span', { class: 'ramp-step' },
      el('span', { class: 'swatch', style: { background: NO_DATA_COLOR } }), t('ramp.noHouseholds')));
}

function drawNearby() {
  layers.nearby.clearLayers();
  for (const other of countedFacilities()) {
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
  const { census, area_km2: area } = surroundings;
  const facilities = countedFacilities();
  const radius = census.radius;
  const beds = facilities.reduce((sum, other) => sum + (other.beds || 0), 0) + (facility.beds || 0);
  const physicians = facilities.reduce((sum, other) => sum + (other.physicians || 0), 0) + (facility.physicians || 0);
  const per10k = (count) => t('sur.per10k', {
    value: radius.population ? formatNumber((count / radius.population) * 10000, 1) : '–',
    period: t('period.cnesShort'),
  });
  dom.tiles.replaceChildren(statTiles([
    { label: t('sur.residents'), value: formatCount(radius.population), note: t('sur.tracts', { count: formatCount(radius.tracts) }) },
    { label: t('sur.households'), value: formatCount(radius.households), note: t('sur.censusNote') },
    { label: t('sur.density'), value: formatCount(Math.round((radius.population || 0) / area)), note: t('sur.censusNote') },
    { label: t('sur.others'), value: formatCount(facilities.length), note: t('sur.withinRadius', { period: t('period.cnesShort') }) },
    { label: t('tile.beds'), value: formatCount(beds), note: per10k(beds) },
    { label: t('tile.physicians'), value: formatCount(physicians), note: per10k(physicians) },
  ]));
}

function renderNearby() {
  const facilities = countedFacilities();
  const hidden = surroundings.facilities.length - facilities.length;
  const hiddenNote = hidden ? t('sur.hiddenPrivate', { count: formatCount(hidden) }) : null;

  const counts = new Map();
  for (const other of facilities) counts.set(other.type, (counts.get(other.type) || 0) + 1);
  const byType = [...counts.entries()]
    .map(([type, value]) => ({ label: typeInfo(type).label, value, color: typeInfo(type).color }))
    .sort((a, b) => b.value - a.value);

  dom.nearbyTypes.replaceChildren(section(t('sur.byType'), byType.length ? barList(byType) : null, {
    hint: byType.length ? t('sur.byTypeHint', { cnes: t('period.cnes') }) : null,
    emptyText: [t('sur.noOthers'), hiddenNote].filter(Boolean).join(' '),
  }));
  if (byType.length) {
    const used = new Set(facilities.map((other) => typeInfo(other.type).group));
    dom.nearbyTypes.append(el('div', { class: 'ramp-legend' }, TYPE_GROUPS
      .filter((group) => used.has(group.id))
      .map((group) => el('span', { class: 'ramp-step' },
        el('span', { class: 'dot', style: { background: group.color } }), pick(group.label)))));
    if (hiddenNote) dom.nearbyTypes.append(el('p', { class: 'hint', text: hiddenNote }));
  }

  const nearest = facilities.slice(0, NEAREST_SHOWN);
  const table = nearest.length ? el('table', { class: 'table' },
    el('thead', {}, el('tr', {},
      el('th', { text: t('sur.col.facility') }), el('th', { text: t('sur.col.type') }),
      el('th', { class: 'num', text: t('sur.col.distance') }), el('th', { class: 'num', text: t('sur.col.beds') }))),
    el('tbody', {}, nearest.map((other) => el('tr', {},
      el('td', {}, el('a', { href: `facility.html?cnes=${other.cnes}`, text: other.name })),
      el('td', { text: typeInfo(other.type).label }),
      el('td', { class: 'num', text: formatDistance(other.distance_m) }),
      el('td', { class: 'num', text: formatCount(other.beds) }))))) : null;
  dom.nearbyList.replaceChildren(section(t('sur.nearest'), table, {
    hint: facilities.length > NEAREST_SHOWN
      ? t('sur.nearestOf', { shown: NEAREST_SHOWN, total: formatCount(facilities.length), cnes: t('period.cnes') })
      : t('sur.nearestHint', { cnes: t('period.cnes') }),
    emptyText: t('sur.noOthers'),
  }));
}

/** The parts that depend on which nearby facilities are counted. */
function renderFacilityParts() {
  drawNearby();
  renderTiles();
  renderNearby();
}

function renderSurroundings() {
  const place = surroundings.location;
  dom.locationLine.textContent = place ? t('sur.location', {
    place: place.district && place.district !== place.municipality ? `${place.district}, ${place.municipality}` : place.municipality,
    tract: place.tract,
  }) : '';
  layers.circle.setRadius(surroundings.radius_m);
  map.fitBounds(layers.circle.getBounds(), { padding: [16, 16] });
  drawTracts();
  renderTerritory(surroundings);
  renderFacilityParts();
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
    dom.tiles.replaceChildren(el('p', { class: 'notice is-error', text: t('sur.loadError', { message: error.message }) }));
  } finally {
    if (pendingRequest === controller) dom.body.classList.remove('is-loading');
  }
}

// The narrative comes from a separate service; the page works without it.
async function loadNarrative() {
  if (!hasNarrative()) return;
  pendingNarrative?.abort();
  const controller = new AbortController();
  pendingNarrative = controller;
  renderNarrativeState(dom.narrative, 'narrative.loading');
  try {
    const body = await getNarrative(cnes, Number(dom.radius.value), { lang, publicOnly: !showPrivate }, controller.signal);
    if (!controller.signal.aborted) renderNarrative(dom.narrative, body);
  } catch (error) {
    if (error.name !== 'AbortError') renderNarrativeState(dom.narrative, 'narrative.unavailable');
  }
}

function onRadiusInput() {
  const radius = Number(dom.radius.value);
  dom.radiusValue.textContent = formatDistance(radius);
  layers?.circle.setRadius(radius);
  clearTimeout(requestTimer);
  requestTimer = setTimeout(() => {
    loadSurroundings();
    loadNarrative();
  }, REQUEST_DELAY_MS);
}

async function init() {
  if (!cnes) {
    dom.root.replaceChildren(el('p', { class: 'notice', text: t('page.noneSelected') }));
    return;
  }
  document.getElementById('back').href = `index.html?cnes=${encodeURIComponent(cnes)}`;

  let row;
  try {
    row = await getFacility(cnes);
  } catch (error) {
    dom.root.replaceChildren(el('p', { class: 'notice is-error', text: t('panel.loadError', { message: error.message }) }));
    return;
  }
  if (!row) {
    dom.root.replaceChildren(el('p', { class: 'notice', text: t('page.unknownCnes', { cnes }) }));
    return;
  }

  document.title = `${facilityName(row)} · ${t('brand')}`;
  dom.root.replaceChildren(facilityHeader(row, 'h1'), renderFacility(row));

  if (!row.coord) {
    dom.root.append(el('p', { class: 'notice', text: `${t('page.noSurroundings')} ${coordStatusNote(row.coord_status)}` }));
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
    const limit = minRadius > step ? ` ${t('sur.radiusLimit', { radius: formatDistance(minRadius) })}` : '';
    dom.locationLine.after(el('p', { class: 'notice', text: note + limit }));
  }

  dom.indicator.replaceChildren(...INDICATORS.map((indicator) =>
    el('option', { value: indicator.id, text: indicator.label })));
  dom.publicOnly.checked = !showPrivate;
  document.getElementById('map-hint').textContent = t('sur.mapHint', { census: t('period.census'), cnes: t('period.cnes') });
  dom.surroundings.hidden = false;
  dom.radius.addEventListener('input', onRadiusInput);
  dom.indicator.addEventListener('change', () => surroundings && drawTracts());
  dom.publicOnly.addEventListener('change', () => {
    showPrivate = !dom.publicOnly.checked;
    setPref(PUBLIC_ONLY_PREF, dom.publicOnly.checked);
    if (surroundings) renderFacilityParts();
    loadNarrative();
  });
  loadSurroundings();
  loadNarrative();
}

init();
