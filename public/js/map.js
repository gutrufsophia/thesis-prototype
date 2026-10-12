// Map page: every locatable facility as a point, with search, category filters
// and a side panel for the selected facility.

import { getFacility, getFacilityPoints } from './api.js';
import { el } from './charts.js';
import { facilityHeader, renderFacility } from './facility-view.js';
import {
  APPROXIMATE_SOURCES, COORD_STATUS, TYPE_GROUPS, formatCnes, formatCount, positionNote, typeInfo,
} from './fields.js';

const RMSP_CENTER = [-23.55, -46.63];
const MAX_SEARCH_RESULTS = 12;
// Groups with fewer, larger facilities are drawn last so they stay on top
const DRAW_ORDER = ['diagnostic', 'specialised', 'primary', 'emergency', 'hospital'];

const map = L.map('map', { preferCanvas: true, zoomControl: false }).setView(RMSP_CENTER, 10);
L.control.zoom({ position: 'topright' }).addTo(map);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 19,
}).addTo(map);

const renderer = L.canvas({ padding: 0.5, tolerance: 5 });
const groupLayers = Object.fromEntries(TYPE_GROUPS.map((group) => [group.id, L.layerGroup()]));
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
  legendItems: document.getElementById('legend-items'),
};

let facilities = [];   // located and unlocated, each with a precomputed search key
let byCnes = new Map();
let selectionToken = 0;

function searchKey(text) {
  return text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

function drawPoints(located) {
  for (const facility of located) {
    const info = typeInfo(facility.type);
    // approximate positions are drawn hollow so they are never read as exact
    const style = APPROXIMATE_SOURCES.has(facility.coordSource)
      ? { color: info.color, weight: 2, fillColor: '#fcfcfb', fillOpacity: 0.85 }
      : { color: '#fcfcfb', weight: 1, fillColor: info.color, fillOpacity: 0.9 };
    L.circleMarker([facility.lat, facility.lon], { renderer, radius: 5, ...style })
      .on('click', () => select(facility.cnes))
      .addTo(groupLayers[info.group]);
  }
  for (const id of DRAW_ORDER) groupLayers[id].addTo(map);
}

function buildLegend(located) {
  const counts = {};
  for (const facility of located) {
    const { group } = typeInfo(facility.type);
    counts[group] = (counts[group] || 0) + 1;
  }
  for (const group of TYPE_GROUPS) {
    const checkbox = el('input', { type: 'checkbox', checked: '' });
    checkbox.addEventListener('change', () => {
      if (checkbox.checked) groupLayers[group.id].addTo(map);
      else groupLayers[group.id].remove();
      // keep the stacking order stable after a layer is re-added
      for (const id of DRAW_ORDER) {
        if (map.hasLayer(groupLayers[id])) groupLayers[id].eachLayer((layer) => layer.bringToFront());
      }
      if (map.hasLayer(selectionRing)) selectionRing.bringToFront();
    });
    dom.legendItems.append(el('label', { class: 'legend-item' },
      checkbox,
      el('span', { class: 'dot', style: { background: group.color } }),
      el('span', { class: 'legend-label', text: group.label }),
      el('span', { class: 'legend-count', text: formatCount(counts[group.id] || 0) })));
  }
}

function showDetail(...children) {
  dom.detail.replaceChildren(
    el('button', { class: 'link-button', type: 'button', id: 'close-detail', text: '← All facilities' }),
    ...children.filter(Boolean));
  dom.detail.hidden = false;
  dom.intro.hidden = true;
  document.getElementById('close-detail').addEventListener('click', clearSelection);
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

  showDetail(el('p', { class: 'hint', text: `Loading ${facility.name}…` }));
  try {
    const row = await getFacility(facility.cnes);
    if (token !== selectionToken) return;
    if (!row) throw new Error('Facility not found.');
    showDetail(
      facilityHeader(row),
      facility.coordStatus
        ? el('p', { class: 'notice', text: `Not shown on the map. ${COORD_STATUS[facility.coordStatus]}` })
        : null,
      positionNote(row) ? el('p', { class: 'notice', text: positionNote(row) }) : null,
      el('a', { class: 'button', href: `facility.html?cnes=${facility.cnes}`, text: 'More info' }),
      renderFacility(row, { compact: true }));
  } catch (error) {
    if (token !== selectionToken) return;
    showDetail(el('p', { class: 'notice is-error', text: `Could not load this facility: ${error.message}` }));
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
    const button = el('button', { type: 'button' },
      el('span', { class: 'result-name', text: facility.name }),
      el('span', { class: 'result-meta', text:
        `${typeInfo(facility.type).label} · CNES ${formatCnes(facility.cnes)}${facility.coordStatus ? ' · not on map' : ''}` }));
    button.addEventListener('click', () => {
      dom.results.hidden = true;
      dom.search.value = facility.name;
      select(facility.cnes, { fly: true });
    });
    return el('li', {}, button);
  }) : [el('li', { class: 'empty', text: 'No facility matches.' })]));
  dom.results.hidden = false;
}

async function init() {
  try {
    const { located, unlocated } = await getFacilityPoints();
    facilities = [...located, ...unlocated].map((facility) => ({
      ...facility,
      key: `${searchKey(facility.name || '')} ${formatCnes(facility.cnes)}`,
    }));
    byCnes = new Map(facilities.map((facility) => [facility.cnes, facility]));
    drawPoints(located);
    buildLegend(located);
    const corrected = located.filter((facility) => facility.coordSource === 'cnefe_corrected').length;
    const geocoded = located.filter((facility) => facility.coordSource !== 'cnes').length - corrected;
    const approximate = located.filter((facility) => APPROXIMATE_SOURCES.has(facility.coordSource)).length;
    dom.status.textContent =
      `${formatCount(located.length)} facilities on the map. ${formatCount(geocoded)} of them were placed from their street address because the registry had no usable coordinate; ${formatCount(approximate)} of those are approximate and drawn as hollow points. Another ${formatCount(corrected)} had a registry coordinate that did not match their own street address and were moved to the address. ${formatCount(unlocated.length)} could not be placed and can only be found through search.`;

    const initial = new URLSearchParams(location.search).get('cnes');
    if (initial) select(initial, { fly: true });
  } catch (error) {
    dom.status.textContent = `Could not load facilities: ${error.message}`;
    dom.status.classList.add('is-error');
  }
}

dom.search.addEventListener('input', runSearch);
dom.search.addEventListener('focus', runSearch);
document.addEventListener('click', (event) => {
  if (!event.target.closest('.panel-top')) dom.results.hidden = true;
});
document.getElementById('legend').addEventListener('submit', (event) => event.preventDefault());

init();
