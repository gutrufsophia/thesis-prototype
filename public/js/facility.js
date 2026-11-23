// Facility page, laid out like a CulturaEduca facility page: a map banner, then tabs for the
// generated narrative, the facility record, the census of the radius, the health indicators
// (district and municipality) and the other facilities in the radius.

import { getFacility, getHospitalStays, getNarrative, getSurroundings, hasNarrative } from './api.js';
import { about, el, keyValues, moreRows, section, statTiles } from './charts.js';
import { deathFigures, renderFacility } from './facility-view.js';
import { dataTable, legend, scatter } from './plots.js';
import { renderNarrative, renderNarrativeState } from './narrative.js';
import { renderPeers } from './peers.js';
import { setupTabs } from './tabs.js';
import { renderTerritory } from './territory.js';
import {
  TYPE_GROUPS, coordStatusNote, facilityAddress, facilityName, formatCnes, formatCount, formatDistance,
  formatNumber, formatPercent, positionNote, typeInfo,
} from './fields.js';
import { applyStaticTranslations, getPref, lang, pick, setPref, t } from './i18n.js';

const REQUEST_DELAY_MS = 300;
const PUBLIC_ONLY_PREF = 'publicOnly';
const NO_DATA_COLOR = '#e1e0d9';
const TRACT_OUTLINE = '#2a78d6';
// Sequential blue ramp, light to dark: more of the indicator is darker
const RAMP = ['#cde2fb', '#9ec5f4', '#5598e7', '#256abf', '#0d366b'];
// Map handlers that stay off while the map is a banner, so the page scrolls over it
const MAP_HANDLERS = ['dragging', 'touchZoom', 'doubleClickZoom', 'boxZoom', 'keyboard'];

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
    id: 'income',
    label: t('ind.income'),
    value: (p) => p.income,
    breaks: [1650, 2700, 5000, 10000],
    format: (value) => `R$ ${formatNumber(value)}`,
  },
  {
    id: 'primary_distance',
    label: t('ind.primaryDistance'),
    value: (p) => p.dist_primary_m,
    breaks: [500, 1000, 2000, 4000],
    format: formatDistance,
  },
];

// Where the data behind a narrative sentence is shown: a map indicator first, else a card.
const INDICATOR_OF_FACT = {
  sewage: 'no_sewage', precarious: 'precarious', garbage: 'no_garbage', crowding: 'crowding', crowded: 'crowding',
  access: 'primary_distance',
};
const INDICATOR_OF_PEER = {
  precarious: 'precarious', off_network: 'no_sewage', no_garbage: 'no_garbage', crowded: 'crowding',
  far_primary: 'primary_distance', income: 'income',
};
const CARD_OF_FACT = {
  profile: 'panel-record', beds: 'panel-record', staff: 'panel-record', admissions: 'panel-record', stay: 'panel-record',
  deaths: 'record-deaths', casemix: 'record-deaths',
  position: 'record-location',
  residents: 's-summary', territory: 's-peers', peer: 's-peers', need_supply: 's-peers',
  sewage: 's-sanitation', precarious: 's-sanitation', garbage: 's-sanitation',
  crowding: 's-housing', crowded: 's-housing',
  access: 's-access',
  dengue: 'h-environment', lepto: 'h-environment',
  tb: 'h-tb', tb_district: 'h-tb', surprise_tb: 'h-tb',
  teen: 'h-maternal', teen_district: 'h-maternal', preterm: 'h-maternal', surprise_teen: 'h-maternal',
  mortality: 'h-mortality',
  network: 'n-groups',
};

applyStaticTranslations();
document.title = t('page.title');

const cnes = new URLSearchParams(location.search).get('cnes');
const $ = (id) => document.getElementById(id);
const dom = {
  hero: $('hero'),
  head: $('facility-head'),
  expand: $('expand-map'),
  mapPanel: $('map-panel'),
  indicator: $('indicator'),
  mapLegend: $('map-legend'),
  radius: $('radius'),
  radiusValue: $('radius-value'),
  publicOnly: $('public-only'),
  record: $('facility-root'),
  narrative: $('narrative'),
  netSummary: $('n-summary'),
  netGroups: $('n-groups'),
  livePanels: [...document.querySelectorAll('.live-panel')],
};
// The tab bar sticks just under the band, whose height changes when it wraps
const band = document.querySelector('.band');
new ResizeObserver(() => document.documentElement.style.setProperty('--band-height', `${band.offsetHeight}px`)).observe(band);
const tabs = setupTabs($('tabs'), { initial: hasNarrative() ? 'story' : 'record' });

let row = null;
let facility = null;
let surroundings = null;
let narrative = null;
let map = null;
let zoomControl = null;
let attribution = null;
let layers = null;
let expanded = false;
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

// ---------- Header ----------

function renderHead() {
  const info = typeInfo(row.tipo_equipamento);
  dom.head.replaceChildren(
    el('span', { class: 'avatar', style: { '--type': info.color }, 'aria-hidden': 'true' }),
    el('div', { class: 'facility-title' },
      el('h1', { text: facilityName(row) }),
      el('p', { class: 'facility-sub', text: `${info.label} · ${info.groupLabel}` }),
      el('p', { class: 'facility-sub', text: facilityAddress(row) })));
}

function renderCrumbs() {
  const place = surroundings.location;
  const municipality = $('crumb-municipality');
  const district = $('crumb-district');
  municipality.textContent = place?.municipality || '';
  municipality.hidden = !place?.municipality;
  district.textContent = place?.district || '';
  district.hidden = !place?.district || place.district === place.municipality;
}

// ---------- Map banner ----------

function setupMap() {
  const position = [surroundings.facility.lat, surroundings.facility.lon];
  map = L.map('mini-map', {
    preferCanvas: true, zoomControl: false, attributionControl: false, scrollWheelZoom: false, zoomSnap: 0.25,
    ...Object.fromEntries(MAP_HANDLERS.map((handler) => [handler, false])),
  }).setView(position, 14);
  zoomControl = L.control.zoom({ position: 'topleft' });
  // Top right while the header covers the bottom of the banner; the indicator panel takes that corner when expanded
  attribution = L.control.attribution({ position: 'topright' }).addTo(map);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  }).addTo(map);
  layers = {
    tracts: L.layerGroup().addTo(map),
    circle: L.circle(position, {
      radius: Number(dom.radius.value), color: '#0b0b0b', weight: 1.5, dashArray: '4 4', fill: false, interactive: false,
    }).addTo(map),
    nearby: L.layerGroup().addTo(map),
    self: L.circleMarker(position, {
      radius: 8, color: '#fcfcfb', weight: 2, fillColor: '#0b0b0b', fillOpacity: 1,
    }).bindTooltip(facility.name).addTo(map),
  };
}

function fitRadius() {
  map.fitBounds(layers.circle.getBounds(), { padding: expanded ? [24, 24] : [12, 12] });
}

function setExpanded(on) {
  expanded = on;
  dom.hero.classList.toggle('is-expanded', on);
  dom.expand.setAttribute('aria-expanded', String(on));
  dom.expand.textContent = t(on ? 'hero.collapse' : 'hero.expand');
  dom.mapPanel.hidden = !on;
  for (const handler of MAP_HANDLERS) map[handler][on ? 'enable' : 'disable']();
  if (on) zoomControl.addTo(map);
  else zoomControl.remove();
  attribution.setPosition(on ? 'bottomright' : 'topright');
  map.invalidateSize();
  fitRadius();
  drawTracts();
  drawNearby();
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

// Collapsed, the banner only outlines the tracts in the radius; colour encodes data only when
// the map is expanded and its legend is visible.
function drawTracts() {
  const indicator = currentIndicator();
  layers.tracts.clearLayers();
  L.geoJSON(surroundings.tracts, {
    interactive: expanded,
    style: (feature) => (expanded
      ? { fillColor: rampColor(indicator, feature.properties), fillOpacity: 0.75, color: '#fcfcfb', weight: 1 }
      : { fillColor: TRACT_OUTLINE, fillOpacity: 0.08, color: TRACT_OUTLINE, weight: 1, opacity: 0.5 }),
    onEachFeature: (feature, layer) => {
      if (!expanded) return;
      layer.bindTooltip(() => tractTooltip(feature.properties), { sticky: true });
      layer.on('mouseover', () => layer.setStyle({ color: '#0b0b0b', weight: 2 }));
      layer.on('mouseout', () => layer.setStyle({ color: '#fcfcfb', weight: 1 }));
    },
  }).addTo(layers.tracts);
  // Redrawn tracts would otherwise cover the markers drawn before them on the shared canvas
  layers.nearby.eachLayer((marker) => marker.bringToFront());
  layers.self.bringToFront();
  if (expanded) drawLegend(indicator);
}

function drawLegend(indicator) {
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
    const marker = L.circleMarker([other.lat, other.lon], {
      radius: 5, color: '#fcfcfb', weight: 2, fillColor: info.color, fillOpacity: 1, interactive: expanded,
    });
    if (expanded) {
      marker.bindTooltip(`${other.name} · ${info.label} · ${formatDistance(other.distance_m)}`)
        .on('click', () => { location.href = `facility.html?cnes=${other.cnes}`; });
    }
    marker.addTo(layers.nearby);
  }
  layers.self.bringToFront();
}

// ---------- Record tab ----------

function cnesLink() {
  if (!row.CO_MUNICIPIO_GESTOR) return null;
  const href = `https://cnes.datasus.gov.br/pages/estabelecimentos/ficha/index.jsp?coUnidade=${row.CO_MUNICIPIO_GESTOR}${formatCnes(row.CO_CNES)}`;
  return el('a', { href, target: '_blank', rel: 'noopener', text: t('record.cnesLink') });
}

/** Positioned by street or postcode only, with a margin of error (the hollow dots on the map). */
function approximatePosition(row) {
  return row.coord_source === 'cnefe_street' || row.coord_source === 'cnefe_cep';
}

function renderLocation() {
  const place = surroundings?.location;
  const entries = [
    [t('record.address'), facilityAddress(row)],
    [t('record.municipality'), place?.municipality],
    [t('record.district'), place?.district && place.district !== place.municipality ? place.district : null],
  ].filter(([, value]) => value);
  const link = cnesLink();
  $('record-location').replaceChildren(...[
    el('h3', { text: t('record.location') }),
    keyValues(entries),
    // Only an approximate position changes how the page reads; where it came from is a detail
    approximatePosition(row) ? el('p', { class: 'notice', text: positionNote(row) }) : null,
    moreRows([
      [t('record.tract'), place?.tract],
      [t('record.position'), row.coord ? positionNote(row) || t('record.positionRegistry') : coordStatusNote(row.coord_status)],
    ]),
    link ? el('p', { class: 'hint' }, link) : null,
  ].filter(Boolean));
}

// ---------- Network tab ----------

function renderNetworkSummary() {
  const radius = surroundings.census.radius;
  const facilities = countedFacilities();
  const beds = facilities.reduce((sum, other) => sum + (other.beds || 0), 0) + facility.beds;
  const physicians = facilities.reduce((sum, other) => sum + (other.physicians || 0), 0) + facility.physicians;
  const per10k = (count) => t('sur.per10k', {
    value: radius.population ? formatNumber((count / radius.population) * 10000, 1) : '–',
    period: t('period.cnesShort'),
  });
  const hidden = surroundings.facilities.length - facilities.length;
  const linked = facilities.filter((other) => other.sus_network).length;
  dom.netSummary.replaceChildren(
    statTiles([
      {
        label: t('sur.others'), value: formatCount(facilities.length),
        note: `${t('net.split', { public: formatCount(linked), private: formatCount(facilities.length - linked) })} · CNES ${t('period.cnesShort')}`,
      },
      { label: t('tile.beds'), value: formatCount(beds), note: per10k(beds) },
      { label: t('tile.physicians'), value: formatCount(physicians), note: per10k(physicians) },
    ]),
    ...[hidden ? el('p', { class: 'hint', text: t('sur.hiddenPrivate', { count: formatCount(hidden) }) }) : null,
      about(t('net.summaryHint'))].filter(Boolean));
}

function facilityTable(facilities) {
  return el('table', { class: 'table' },
    el('thead', {}, el('tr', {},
      el('th', { text: t('sur.col.facility') }), el('th', { text: t('sur.col.type') }),
      el('th', { text: t('net.col.sus') }),
      el('th', { class: 'num', text: t('sur.col.distance') }), el('th', { class: 'num', text: t('sur.col.beds') }))),
    el('tbody', {}, facilities.map((other) => el('tr', {},
      el('td', {}, el('a', { href: `facility.html?cnes=${other.cnes}`, text: other.name })),
      el('td', { text: typeInfo(other.type).label }),
      el('td', { text: other.sus_network ? t('yes') : t('no') }),
      el('td', { class: 'num', text: formatDistance(other.distance_m) }),
      el('td', { class: 'num', text: formatCount(other.beds) })))));
}

/** One collapsible row per facility category, as in CulturaEduca's list of nearby facilities. */
function renderNetworkGroups() {
  const open = new Set([...dom.netGroups.querySelectorAll('details[open]')].map((node) => node.dataset.group));
  const facilities = countedFacilities();
  dom.netGroups.replaceChildren(
    el('h3', { class: 'card-title', text: t('net.title', { radius: formatDistance(surroundings.radius_m) }) }),
    about(t('sur.nearestHint', { cnes: t('period.cnes') })),
    ...TYPE_GROUPS.map((group) => {
      const members = facilities.filter((other) => typeInfo(other.type).group === group.id);
      return el('details', { class: 'accordion', dataset: { group: group.id }, open: open.has(group.id) ? '' : null },
        el('summary', {},
          el('span', { class: 'dot', style: { background: group.color } }),
          el('span', { class: 'accordion-label', text: pick(group.label) }),
          el('span', { class: 'accordion-count', text: `(${formatCount(members.length)})` })),
        members.length ? facilityTable(members) : el('p', { class: 'empty', text: t('net.noneInGroup') }));
    }));
}

/** The parts that depend on which nearby facilities are counted. */
function renderFacilityParts() {
  drawNearby();
  renderNetworkSummary();
  renderNetworkGroups();
}

// ---------- Loading ----------

function setLoading(on) {
  for (const panel of dom.livePanels) panel.classList.toggle('is-loading', on);
}

async function loadSurroundings() {
  pendingRequest?.abort();
  const controller = new AbortController();
  pendingRequest = controller;
  setLoading(true);
  try {
    const data = await getSurroundings(cnes, Number(dom.radius.value), controller.signal);
    if (controller.signal.aborted) return;
    surroundings = data;
    if (!map) setupMap();
    layers.circle.setRadius(surroundings.radius_m);
    fitRadius();
    drawTracts();
    renderCrumbs();
    renderLocation();
    renderTerritory(surroundings);
    renderFacilityParts();
    $('load-error').hidden = true;
  } catch (error) {
    if (error.name === 'AbortError') return;
    $('load-error').textContent = t('sur.loadError', { message: error.message });
    $('load-error').hidden = false;
  } finally {
    if (pendingRequest === controller) setLoading(false);
  }
}

// ---------- Narrative ----------

function indicatorOfFact(fact) {
  if (fact !== 'peer') return INDICATOR_OF_FACT[fact];
  const key = narrative?.facts.find((f) => f.id === 'peer')?.slots.indicator?.key?.split(':')[1];
  return INDICATOR_OF_PEER[key];
}

const sentenceLink = {
  title(fact) {
    if (indicatorOfFact(fact)) return t('narrative.selectMap');
    return CARD_OF_FACT[fact] ? t('narrative.selectCard') : null;
  },
  select(fact) {
    const indicator = indicatorOfFact(fact);
    if (indicator && map) {
      dom.indicator.value = indicator;
      if (expanded) drawTracts();
      else setExpanded(true);
      dom.hero.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
    const card = $(CARD_OF_FACT[fact]);
    if (!card) return;
    tabs.reveal(card);
    card.scrollIntoView({ behavior: 'smooth', block: 'start' });
    card.classList.add('is-linked');
    setTimeout(() => card.classList.remove('is-linked'), 2400);
  },
};

// The narrative comes from a separate service; the page works without it.
async function loadNarrative() {
  if (!hasNarrative()) return;
  pendingNarrative?.abort();
  const controller = new AbortController();
  pendingNarrative = controller;
  renderNarrativeState(dom.narrative, 'narrative.loading');
  try {
    const body = await getNarrative(cnes, Number(dom.radius.value), { lang, publicOnly: !showPrivate }, controller.signal);
    if (!controller.signal.aborted) {
      narrative = body;
      if (body.withheld) renderNarrativeState(dom.narrative, 'narrative.withheld');
      else renderNarrative(dom.narrative, body, sentenceLink);
      renderPeers($('s-peers'), body.reference, body.facts, Number(dom.radius.value));
    }
  } catch (error) {
    if (error.name === 'AbortError') return;
    renderNarrativeState(dom.narrative, 'narrative.unavailable');
    $('s-peers').hidden = true;
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

function fail(text, isError = false) {
  dom.head.replaceChildren(el('p', { class: `notice${isError ? ' is-error' : ''}`, text }));
  dom.record.replaceChildren();
  tabs.select('record');
}

// Funnel of observed / expected in-hospital deaths among the region's hospitals, on a log scale
// (database/reference/compute_hospital_mortality.py). Ratios are drawn as log2 and labelled as ratios;
// hospitals without deaths sit at half a death, as in the limits.
const FUNNEL_FLOOR = -4;
const FUNNEL_CEILING = 4.6;

async function renderDeathsFunnel() {
  const target = dom.record.querySelector('.deaths-plot');
  const own = deathFigures(row);
  if (!target || !own) return;
  let data;
  try {
    data = await (await fetch('data/hospital_mortality.json')).json();
  } catch {
    return;
  }
  const clip = (v) => Math.min(FUNNEL_CEILING, Math.max(FUNNEL_FLOOR, v));
  const hospitals = data.points.map(([code, name, admissions, deaths, expected]) => ({ code, name, admissions, deaths, expected }));
  const points = hospitals.map((h) => {
    const ratio = h.deaths / h.expected;
    const y = Math.log2((h.deaths || 0.5) / h.expected);
    return {
      x: h.expected, y: clip(y), label: t('deaths.thisUnit'), highlight: h.code === Number(row.CO_CNES),
      tooltip: [h.name, t('deaths.tooltip', {
        deaths: formatCount(h.deaths), expected: formatNumber(h.expected, 0), ratio: formatNumber(ratio, 2),
      }), y === clip(y) ? null : t('deaths.offScale')].filter(Boolean),
    };
  });
  const xs = hospitals.map((h) => h.expected).filter((v) => v > 0);
  const lo = Math.min(...xs);
  const hi = Math.max(...xs);
  const grid = Array.from({ length: 60 }, (_, i) => lo * (hi / lo) ** (i / 59));
  const limit = (z, sign) => grid.map((e) => [e, clip((sign * z * Math.sqrt(1 / e + data.tau2)) / Math.LN2)]);
  const title = t('deaths.plotTitle');
  target.replaceChildren(
    legend([{ label: t('deaths.otherHospitals') }, { label: t('deaths.thisUnit'), highlight: true }]),
    scatter(points, {
      xLabel: t('deaths.xLabel'), yLabel: t('deaths.yLabel'), xLog: true, title,
      formatX: (v) => (v >= 1 ? formatCount(v) : formatNumber(v, v < 0.1 ? 2 : 1)),
      formatY: (v) => `${formatNumber(2 ** v, v < 0 ? 2 : 0)}×`,
      bands: [
        { points: grid.map((e) => [e, 0]), className: 'is-inner' },
        { points: limit(data.z['95'], 1), className: 'is-inner' }, { points: limit(data.z['95'], -1), className: 'is-inner' },
        { points: limit(data.z['998'], 1) }, { points: limit(data.z['998'], -1) },
      ],
    }),
    el('p', { class: 'hint', text: t('deaths.plotCaption', { count: formatCount(data.hospitals), rate: formatNumber(data.regional_mortality_pct, 1) }) }),
    dataTable([
      { label: t('deaths.table.hospital'), value: (h) => h.name },
      { label: t('deaths.table.admissions'), numeric: true, value: (h) => formatCount(h.admissions) },
      { label: t('deaths.table.deaths'), numeric: true, value: (h) => formatCount(h.deaths) },
      { label: t('deaths.table.expected'), numeric: true, value: (h) => formatNumber(h.expected, 0) },
      { label: t('deaths.table.ratio'), numeric: true, value: (h) => formatNumber(h.deaths / h.expected, 2) },
    ], [...hospitals].sort((a, b) => b.expected - a.expected), t('deaths.table.show')));
}

async function init() {
  if (!cnes) {
    fail(t('page.noneSelected'));
    return;
  }
  $('back').href = `index.html?cnes=${encodeURIComponent(cnes)}`;

  let stays = null;
  try {
    [row, stays] = await Promise.all([getFacility(cnes), getHospitalStays().catch(() => null)]);
  } catch (error) {
    fail(t('panel.loadError', { message: error.message }), true);
    return;
  }
  if (!row) {
    fail(t('page.unknownCnes', { cnes }));
    return;
  }

  document.title = `${facilityName(row)} · ${t('brand')}`;
  renderHead();
  const record = renderFacility(row, { stays });
  record.querySelector('.facility-sections').prepend(el('section', { class: 'block', id: 'record-location' }));
  dom.record.replaceChildren(record);
  renderLocation();
  renderDeathsFunnel();

  if (!row.coord) {
    dom.record.prepend(el('p', { class: 'notice', text: `${t('page.noSurroundings')} ${coordStatusNote(row.coord_status)}` }));
    tabs.select('record');
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
  const note = approximatePosition(row) ? positionNote(row) : null;
  if (note) {
    const limit = minRadius > step ? ` ${t('sur.radiusLimit', { radius: formatDistance(minRadius) })}` : '';
    $('surroundings-scope').after(el('p', { class: 'notice', text: note + limit }));
  }

  dom.indicator.replaceChildren(...INDICATORS.map((indicator) =>
    el('option', { value: indicator.id, text: indicator.label })));
  dom.publicOnly.checked = !showPrivate;
  $('map-hint').textContent = t('sur.mapHint', { census: t('period.census'), cnes: t('period.cnes') });

  dom.hero.classList.remove('is-static');
  for (const id of ['crumb-radius', 'public-only-control', 'expand-map', 'tab-surroundings', 'tab-health', 'tab-network']) {
    $(id).hidden = false;
  }
  $('tab-story').hidden = !hasNarrative();
  tabs.start();

  dom.radius.addEventListener('input', onRadiusInput);
  dom.indicator.addEventListener('change', () => surroundings && drawTracts());
  dom.expand.addEventListener('click', () => map && setExpanded(!expanded));
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
