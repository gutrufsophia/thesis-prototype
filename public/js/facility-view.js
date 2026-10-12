// Renders one facility record. Used by the map's side panel (compact) and by the
// facility page (full).

import { barList, el, section, statTiles } from './charts.js';
import {
  ADMISSIONS, CLIENTELE_FLOW, EQUIPMENT, ICU_BEDS, MANAGEMENT, SHIFTS, SPECIALTIES,
  facilityAddress, facilityName, formatCnes, formatCount, formatNumber, typeInfo,
} from './fields.js';

/** Non-zero entries of `labels` found in `row`, largest first. */
function rankedItems(row, labels) {
  return Object.entries(labels)
    .map(([column, label]) => ({ label, value: Number(row[column]) || 0 }))
    .filter((item) => item.value > 0)
    .sort((a, b) => b.value - a.value);
}

function limited(items, limit) {
  if (!limit || items.length <= limit) return { shown: items, hidden: 0 };
  return { shown: items.slice(0, limit), hidden: items.length - limit };
}

function rankedSection(title, items, { limit, hint, emptyText } = {}) {
  if (!items.length) return section(title, null, { emptyText });
  const { shown, hidden } = limited(items, limit);
  const more = hidden ? `Top ${shown.length} of ${items.length} shown.` : null;
  return section(title, barList(shown), { hint: [hint, more].filter(Boolean).join(' ') });
}

export function typeChip(type) {
  const info = typeInfo(type);
  return el('span', { class: 'chip' },
    el('span', { class: 'dot', style: { background: info.color } }),
    info.label);
}

export function facilityHeader(row, headingTag = 'h2') {
  return el('header', { class: 'facility-header' },
    typeChip(row.tipo_equipamento),
    el(headingTag, { text: facilityName(row) }),
    el('p', { class: 'address', text: facilityAddress(row) }));
}

function profile(row) {
  const entries = [
    ['CNES code', formatCnes(row.CO_CNES)],
    ['Legal name', row.NO_RAZAO_SOCIAL],
    ['Category', typeInfo(row.tipo_equipamento).groupLabel],
    ['Management', MANAGEMENT[row.TP_GESTAO] || row.TP_GESTAO],
    ['Patient flow', CLIENTELE_FLOW[row.Fluxo_Clientela] || 'Not reported'],
    ['Opening hours', SHIFTS[row.CO_TURNO_ATENDIMENTO] || 'Not reported'],
  ];
  return el('dl', { class: 'profile' }, entries.flatMap(([term, value]) => [
    el('dt', { text: term }),
    el('dd', { text: value || '–' }),
  ]));
}

function keyFigures(row) {
  const admissions = Number(row.internacoes_total) || 0;
  return statTiles([
    { label: 'Beds', value: formatCount(row.LEITOS_EXISTENTES), note: `${formatCount(row.LEITOS_SUS)} SUS` },
    { label: 'ICU beds', value: formatCount(row.UTI_TOTAL_EXIST), note: `${formatCount(row.UTI_TOTAL_SUS)} SUS` },
    { label: 'Physicians', value: formatCount(row.total_medicos), note: 'in care teams' },
    { label: 'Nurses', value: formatCount(row.total_enfermeiros), note: 'in care teams' },
    { label: 'Admissions', value: formatCount(admissions) },
    {
      label: 'Mean stay',
      value: admissions ? `${formatNumber(row.media_dias_permanencia, 1)} d` : '–',
    },
  ]);
}

function icuSection(row) {
  const items = ICU_BEDS
    .map(([all, sus, label]) => ({ label, value: Number(row[all]) || 0, note: `${formatCount(row[sus])} SUS` }))
    .filter((item) => item.value > 0);
  return section('ICU beds by type', items.length ? barList(items) : null, {
    emptyText: 'No ICU beds registered.',
  });
}

function workforceSection(row, limit) {
  const items = rankedItems(row, SPECIALTIES);
  return rankedSection('Workforce by specialty', items, {
    limit,
    hint: 'Only professionals registered in care teams (CNES) are counted, so hospital staff are largely absent.',
    emptyText: 'No care-team professionals registered for this facility.',
  });
}

/**
 * @param {object} row  record from infraestrutura_saude
 * @param {{compact?: boolean}} options  compact trims long lists for the side panel
 */
export function renderFacility(row, { compact = false } = {}) {
  const limit = compact ? 5 : 0;
  return el('div', { class: `facility${compact ? ' is-compact' : ''}` },
    keyFigures(row),
    el('div', { class: 'facility-sections' },
      section('Profile', profile(row)),
      icuSection(row),
      workforceSection(row, limit),
      rankedSection('Equipment by category', rankedItems(row, EQUIPMENT), {
        limit,
        hint: 'Units registered in CNES.',
        emptyText: 'No equipment registered.',
      }),
      rankedSection('Admissions by cause', rankedItems(row, ADMISSIONS), {
        limit,
        hint: 'SUS hospital admissions by ICD-10 chapter (SIH).',
        emptyText: 'No SUS hospital admissions recorded: this is not an inpatient unit, or it does not bill SUS.',
      })));
}
