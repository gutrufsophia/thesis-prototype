// Map page: every locatable facility as a point, with search, filters by CNES
// facility type and a side panel for the selected facility.

import { getFacility, getFacilityPoints } from './api.js';
import { el } from './charts.js';
import { facilityHeader, renderFacility } from './facility-view.js';
import {
  APPROXIMATE_SOURCES, FACILITY_TYPES, TYPE_GROUPS, coordStatusNote, formatCnes, formatCount, positionNote, typeInfo,
} from './fields.js';
import { applyStaticTranslations, getPref, pick, setPref, t } from './i18n.js';

const RMSP_CENTER = [-23.55, -46.63];
const MAX_SEARCH_RESULTS = 12;
const PUBLIC_ONLY_PREF = 'publicOnly';
// Groups with fewer, larger facilities are drawn last so they stay on top
const DRAW_ORDER = ['diagnostic', 'specialised', 'primary', 'emergency', 'hospital'];

applyStaticTranslations();
document.title = t('map.title');

const map = L.map('map', { preferCanvas: true, zoomControl: false }).setView(RMSP_CENTER, 10);
L.control.zoom({ position: 'topright' }).addTo(map);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 19,
}).addTo(map);

const renderer = L.canvas({ padding: 0.5, tolerance: 5 });
const selectionRing = L.circleMarker(RMSP_CENTER, {
  renderer, radius: 10, color: '#0b0b0b', weight: 2, fill: false, interactive: false,
});
const popup = L.popup({ closeButton: false, offset: [0, -4] });

const dom = {
  search: document.getElementById('search'),
  results: document.getElementById('search-results'),
  intro: document.getElementById('intro'),
  detail: document.getElementById('detail'),
  status: document.getElementById('status'),
  legend: document.getElementById('legend'),
  legendItems: document.getElementById('legend-items'),
  publicOnly: document.getElementById('public-only'),
};

// One layer per (facility type, public network or not), so both filters are cheap
const layers = new Map();
const checkedTypes = new Set(Object.keys(FACILITY_TYPES));
// Private facilities without a SUS link are shown unless the user asks for the public network only
let showPrivate = !getPref(PUBLIC_ONLY_PREF);
let facilities = [];   // located and unlocated, each with a precomputed search key
let located = [];
let byCnes = new Map();
let selectionToken = 0;
const typeControls = new Map();   // type -> { checkbox, count }
const groupControls = new Map();  // group id -> { checkbox, count, types }

const layerKey = (type, susNetwork) => `${type}|${susNetwork ? 1 : 0}`;

function searchKey(text) {
  return text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

function isVisible(facility) {
  return checkedTypes.has(facility.type) && (facility.susNetwork || showPrivate);
}

function drawPoints() {
  for (const facility of located) {
    const info = typeInfo(facility.type);
    // approximate positions are drawn hollow so they are never read as exact
    const style = APPROXIMATE_SOURCES.has(facility.coordSource)
      ? { color: info.color, weight: 2, fillColor: '#fcfcfb', fillOpacity: 0.85 }
      : { color: '#fcfcfb', weight: 1, fillColor: info.color, fillOpacity: 0.9 };
    const key = layerKey(facility.type, facility.susNetwork);
    if (!layers.has(key)) layers.set(key, L.layerGroup());
    L.circleMarker([facility.lat, facility.lon], { renderer, radius: 5, ...style })
      .on('click', () => select(facility.cnes))
      .addTo(layers.get(key));
  }
}

/** Show or hide each layer according to the filters, keeping the stacking order. */
function syncLayers() {
  for (const groupId of DRAW_ORDER) {
    for (const type of groupControls.get(groupId).types) {
      for (const susNetwork of [false, true]) {
        const layer = layers.get(layerKey(type, susNetwork));
        if (!layer) continue;
        const wanted = checkedTypes.has(type) && (susNetwork || showPrivate);
        if (wanted) {
          layer.addTo(map);
          layer.eachLayer((marker) => marker.bringToFront());
        } else {
          layer.remove();
        }
      }
    }
  }
  if (map.hasLayer(selectionRing)) selectionRing.bringToFront();
}

function updateCounts() {
  const perType = new Map();
  for (const facility of located) {
    if (facility.susNetwork || showPrivate) perType.set(facility.type, (perType.get(facility.type) || 0) + 1);
  }
  for (const [type, control] of typeControls) control.count.textContent = formatCount(perType.get(type) || 0);
  for (const control of groupControls.values()) {
    const checked = control.types.filter((type) => checkedTypes.has(type)).length;
    control.checkbox.checked = checked === control.types.length;
    control.checkbox.indeterminate = checked > 0 && checked < control.types.length;
    control.count.textContent = formatCount(control.types.reduce((sum, type) => sum + (perType.get(type) || 0), 0));
  }
}

function updateStatus() {
  const shown = located.filter(isVisible);
  const hiddenPrivate = located.filter((facility) => !facility.susNetwork).length;
  const parts = [t('map.status.shown', { shown: formatCount(shown.length) })];
  if (!showPrivate && hiddenPrivate) parts.push(t('map.status.private', { count: formatCount(hiddenPrivate) }));
  const corrected = shown.filter((facility) => facility.coordSource === 'cnefe_corrected').length;
  parts.push(t('map.status.geocoded', {
    geocoded: formatCount(shown.filter((facility) => facility.coordSource !== 'cnes').length - corrected),
    approximate: formatCount(shown.filter((facility) => APPROXIMATE_SOURCES.has(facility.coordSource)).length),
    corrected: formatCount(corrected),
  }));
  const unlocated = facilities.filter((facility) => facility.lat === undefined && (facility.susNetwork || showPrivate)).length;
  if (unlocated) parts.push(t('map.status.unlocated', { count: formatCount(unlocated) }));
  dom.status.textContent = parts.join(' ');
}

function refresh() {
  syncLayers();
  updateCounts();
  updateStatus();
}

function buildLegend() {
  for (const group of TYPE_GROUPS) {
    const types = Object.keys(FACILITY_TYPES).filter((type) => FACILITY_TYPES[type].group === group.id);
    const groupCheckbox = el('input', { type: 'checkbox', checked: '' });
    const groupCount = el('span', { class: 'legend-count' });
    groupControls.set(group.id, { checkbox: groupCheckbox, count: groupCount, types });
    groupCheckbox.addEventListener('change', () => {
      for (const type of types) {
        if (groupCheckbox.checked) checkedTypes.add(type);
        else checkedTypes.delete(type);
        typeControls.get(type).checkbox.checked = groupCheckbox.checked;
      }
      refresh();
    });
    dom.legendItems.append(el('label', { class: 'legend-item is-group' },
      groupCheckbox,
      el('span', { class: 'dot', style: { background: group.color } }),
      el('span', { class: 'legend-label', text: pick(group.label) }),
      groupCount));

    for (const type of types) {
      const checkbox = el('input', { type: 'checkbox', checked: '' });
      const count = el('span', { class: 'legend-count' });
      typeControls.set(type, { checkbox, count });
      checkbox.addEventListener('change', () => {
        if (checkbox.checked) checkedTypes.add(type);
        else checkedTypes.delete(type);
        refresh();
      });
      dom.legendItems.append(el('label', { class: 'legend-item is-type' },
        checkbox, el('span', { class: 'legend-label', text: typeInfo(type).label }), count));
    }
  }

  dom.publicOnly.checked = !showPrivate;
  dom.publicOnly.addEventListener('change', () => {
    showPrivate = !dom.publicOnly.checked;
    setPref(PUBLIC_ONLY_PREF, dom.publicOnly.checked);
    refresh();
  });
  // on a phone the filter list would cover the map
  if (window.matchMedia('(max-width: 800px)').matches) dom.legend.open = false;
}

function showDetail(...children) {
  const back = el('button', { class: 'link-button', type: 'button', text: t('panel.back') });
  back.addEventListener('click', clearSelection);
  dom.detail.replaceChildren(back, ...children.filter(Boolean));
  dom.detail.hidden = false;
  dom.intro.hidden = true;
  document.getElementById('panel-body').scrollTop = 0;
}

function clearSelection() {
  selectionToken += 1;
  dom.detail.hidden = true;
  dom.intro.hidden = false;
  selectionRing.remove();
  map.closePopup(popup);
  history.replaceState(null, '', location.pathname);
}

async function select(cnes, { fly = false } = {}) {
  const facility = byCnes.get(Number(cnes));
  if (!facility) return;
  const token = ++selectionToken;
  history.replaceState(null, '', `?cnes=${facility.cnes}`);

  if (facility.lat !== undefined) {
    const position = [facility.lat, facility.lon];
    selectionRing.setLatLng(position).addTo(map).bringToFront();
    popup.setLatLng(position).setContent(el('div', { class: 'popup' },
      el('strong', { text: facility.name }),
      el('span', { text: typeInfo(facility.type).label }))).openOn(map);
    if (fly) map.flyTo(position, Math.max(map.getZoom(), 15), { duration: 0.6 });
  } else {
    selectionRing.remove();
    map.closePopup(popup);
  }

  showDetail(el('p', { class: 'hint', text: t('panel.loading', { name: facility.name }) }));
  try {
    const row = await getFacility(facility.cnes);
    if (token !== selectionToken) return;
    if (!row) throw new Error(t('panel.notFound'));
    const note = (text) => (text ? el('p', { class: 'notice', text }) : null);
    showDetail(
      facilityHeader(row),
      note(facility.coordStatus && `${t('panel.notOnMap')} ${coordStatusNote(facility.coordStatus)}`),
      note(!facility.susNetwork && !showPrivate && facility.lat !== undefined && t('panel.hiddenPrivate')),
      note(positionNote(row)),
      el('a', { class: 'button', href: `facility.html?cnes=${facility.cnes}`, text: t('panel.more') }),
      renderFacility(row, { compact: true }));
  } catch (error) {
    if (token !== selectionToken) return;
    showDetail(el('p', { class: 'notice is-error', text: t('panel.loadError', { message: error.message }) }));
  }
}

function runSearch() {
  const query = searchKey(dom.search.value.trim());
  if (query.length < 2) {
    dom.results.hidden = true;
    return;
  }
  const matches = [];
  for (const facility of facilities) {
    if (facility.key.includes(query)) matches.push(facility);
    if (matches.length === MAX_SEARCH_RESULTS) break;
  }
  dom.results.replaceChildren(...(matches.length ? matches.map((facility) => {
    const meta = [
      typeInfo(facility.type).label,
      `CNES ${formatCnes(facility.cnes)}`,
      facility.coordStatus && t('search.notOnMap'),
      !facility.susNetwork && t('search.private'),
    ].filter(Boolean).join(' · ');
    const button = el('button', { type: 'button' },
      el('span', { class: 'result-name', text: facility.name }),
      el('span', { class: 'result-meta', text: meta }));
    button.addEventListener('click', () => {
      dom.results.hidden = true;
      dom.search.value = facility.name;
      select(facility.cnes, { fly: true });
    });
    return el('li', {}, button);
  }) : [el('li', { class: 'empty', text: t('search.none') })]));
  dom.results.hidden = false;
}

async function init() {
  try {
    const points = await getFacilityPoints();
    located = points.located;
    // public-network facilities first, so they lead the search results
    facilities = [...points.located, ...points.unlocated]
      .map((facility) => ({ ...facility, key: `${searchKey(facility.name || '')} ${formatCnes(facility.cnes)}` }))
      .sort((a, b) => Number(b.susNetwork) - Number(a.susNetwork));
    byCnes = new Map(facilities.map((facility) => [facility.cnes, facility]));
    drawPoints();
    buildLegend();
    refresh();

    const initial = new URLSearchParams(location.search).get('cnes');
    if (initial) select(initial, { fly: true });
  } catch (error) {
    dom.status.textContent = t('map.loadError', { message: error.message });
    dom.status.classList.add('is-error');
  }
}

dom.search.addEventListener('input', runSearch);
dom.search.addEventListener('focus', runSearch);
document.addEventListener('click', (event) => {
  if (!event.target.closest('.panel-top')) dom.results.hidden = true;
});
dom.legend.addEventListener('submit', (event) => event.preventDefault());

init();
