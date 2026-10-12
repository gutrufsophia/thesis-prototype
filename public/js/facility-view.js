// Renders one facility record. Used by the map's side panel (compact) and by the
// facility page (full).

import { barList, el, section, statTiles } from './charts.js';
import {
  ADMISSIONS, EQUIPMENT, ICU_BEDS, SPECIALTIES,
  facilityAddress, facilityName, flowLabel, formatCnes, formatCount, formatNumber,
  legalSphereLabel, managementLabel, shiftLabel, typeInfo,
} from './fields.js';
import { pick, t } from './i18n.js';

/** Reference periods of the sources, for the `{cnes}` and `{sih}` placeholders. */
const sources = () => ({ cnes: t('period.cnes'), sih: t('period.sih') });

/** Non-zero entries of `labels` found in `row`, largest first. */
function rankedItems(row, labels) {
  return Object.entries(labels)
    .map(([column, label]) => ({ label: pick(label), value: Number(row[column]) || 0 }))
    .filter((item) => item.value > 0)
    .sort((a, b) => b.value - a.value);
}

function rankedSection(title, items, { limit, hint, emptyText } = {}) {
  if (!items.length) return section(title, null, { emptyText });
  const shown = limit && items.length > limit ? items.slice(0, limit) : items;
  const more = shown.length < items.length ? t('topShown', { shown: shown.length, total: items.length }) : null;
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
    [t('profile.cnes'), formatCnes(row.CO_CNES)],
    [t('profile.legalName'), row.NO_RAZAO_SOCIAL],
    [t('profile.type'), typeInfo(row.tipo_equipamento).label],
    [t('profile.sector'), legalSphereLabel(row.esfera_juridica)],
    [t('profile.sus'), row.atende_sus ? t('yes') : t('no')],
    [t('profile.management'), managementLabel(row.TP_GESTAO)],
    [t('profile.flow'), flowLabel(row.Fluxo_Clientela)],
    [t('profile.hours'), shiftLabel(row.CO_TURNO_ATENDIMENTO)],
  ];
  return el('dl', { class: 'profile' }, entries.flatMap(([term, value]) => [
    el('dt', { text: term }),
    el('dd', { text: value || '–' }),
  ]));
}

function keyFigures(row) {
  const admissions = Number(row.internacoes_total) || 0;
  const sus = (column) => t('tile.susNote', { count: formatCount(row[column]) });
  return statTiles([
    { label: t('tile.beds'), value: formatCount(row.LEITOS_EXISTENTES), note: sus('LEITOS_SUS') },
    { label: t('tile.icu'), value: formatCount(row.UTI_TOTAL_EXIST), note: sus('UTI_TOTAL_SUS') },
    { label: t('tile.physicians'), value: formatCount(row.total_medicos) },
    { label: t('tile.nurses'), value: formatCount(row.total_enfermeiros) },
    { label: t('tile.admissions'), value: formatCount(admissions), note: t('period.sihShort') },
    {
      label: t('tile.stay'),
      value: admissions ? t('tile.days', { value: formatNumber(row.media_dias_permanencia, 1) }) : '–',
      note: t('period.sihShort'),
    },
  ]);
}

function icuSection(row) {
  const items = ICU_BEDS
    .map(([all, sus, label]) => ({
      label: pick(label),
      value: Number(row[all]) || 0,
      note: t('tile.susNote', { count: formatCount(row[sus]) }),
    }))
    .filter((item) => item.value > 0);
  return section(t('icu.title'), items.length ? barList(items) : null, {
    hint: items.length ? t('icu.hint', sources()) : null, emptyText: t('icu.empty'),
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
    el('p', { class: 'hint', text: t('figures.sources', sources()) }),
    el('div', { class: 'facility-sections' },
      section(t('profile.title'), profile(row)),
      icuSection(row),
      rankedSection(t('workforce.title'), rankedItems(row, SPECIALTIES), {
        limit, hint: t('workforce.hint', sources()), emptyText: t('workforce.empty'),
      }),
      rankedSection(t('equipment.title'), rankedItems(row, EQUIPMENT), {
        limit, hint: t('equipment.hint', sources()), emptyText: t('equipment.empty'),
      }),
      rankedSection(t('admissions.title'), rankedItems(row, ADMISSIONS), {
        limit, hint: t('admissions.hint', sources()), emptyText: t('admissions.empty'),
      })));
}
