// Renders one facility record. Used by the map's side panel (compact) and by the
// facility page (full).

import { barList, el, keyValues, section, statTiles } from './charts.js';
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
  return keyValues(entries);
}

const HOSPITAL_TYPES = ['Hospital Geral', 'Hospital Especializado', 'Unidade Mista'];

// Thresholds of rule C24 (backend-core/config/rules.json): below them the text does not compare
const DEATHS_MIN_ADMISSIONS = 100;
const DEATHS_MIN_EXPECTED = 5;
// Rule C23d: referred patients recorded as elective
const ELECTIVE_CODING_MIN = 80;
const REFERRAL_ONLY = 'Atendimento de Demanda Referenciada';

/** In-hospital death figures, or null when the facility has none (database/reference/compute_hospital_mortality.py). */
export function deathFigures(row) {
  const admissions = Number(row.internacoes_total) || 0;
  const expected = Number(row.obitos_esperados);
  if (!admissions || row.obitos_sus === null || row.obitos_sus === undefined || !(expected > 0)) return null;
  const deaths = Number(row.obitos_sus);
  return {
    admissions, deaths, expected, band: row.mortalidade_faixa,
    rate: (100 * deaths) / admissions,
    expectedRate: (100 * expected) / admissions,
    ratio: deaths / expected,
    few: admissions < DEATHS_MIN_ADMISSIONS || expected < DEATHS_MIN_EXPECTED,
    profile: row.mortalidade_perfil && typeof row.mortalidade_perfil === 'object' ? row.mortalidade_perfil : null,
  };
}

/** What sets the expected rate apart from the regional one, factor by factor. */
function profileRows(profile) {
  const share = (own, region) => t('deaths.share', { own: formatNumber(own, 1), region: formatNumber(region, 1) });
  const signed = (value) => `${value > 0 ? '+' : value < 0 ? '\u2212' : ''}${formatNumber(Math.abs(value), 1)}`;
  const parts = profile.shapley_pp || {};
  const rate = Number(profile.capitulo_taxa_regiao);
  return [
    [t('deaths.regional'), `${formatNumber(profile.taxa_regiao, 1)}%`],
    [t('deaths.shift'), t('deaths.shiftValue', {
      diagnosis: signed(parts.diagnostico), age: signed(parts.idade), urgency: signed(parts.carater),
    })],
    [t('deaths.chapterShare', { chapter: pick(ADMISSIONS[profile.capitulo]).toLowerCase() }), t('deaths.chapterValue', {
      own: formatNumber(profile.capitulo_pct, 1), region: formatNumber(profile.capitulo_regiao_pct, 1),
      rate: formatNumber(rate, rate < 1 ? 2 : 1),
    })],
    [t('deaths.old'), share(profile.idosos_pct, profile.idosos_regiao_pct)],
    [t('deaths.urgent'), share(profile.urgencia_pct, profile.urgencia_regiao_pct)],
  ];
}

function electiveCoding(row, profile) {
  return Boolean(profile) && row.Fluxo_Clientela === REFERRAL_ONLY &&
    100 - Number(profile.urgencia_pct) >= ELECTIVE_CODING_MIN && Number(profile.shapley_pp?.carater) < 0;
}

function keyFigures(row, stays) {
  const admissions = Number(row.internacoes_total) || 0;
  const deaths = deathFigures(row);
  const sus = (column) => t('tile.susNote', { count: formatCount(row[column]) });
  // SIH covers SUS admissions only: a private hospital without SUS would otherwise show 0
  const sih = row.atende_sus || admissions > 0;
  return statTiles([
    { label: t('tile.beds'), value: formatCount(row.LEITOS_EXISTENTES), note: sus('LEITOS_SUS') },
    {
      label: t('tile.icu'), value: formatCount(row.UTI_TOTAL_EXIST),
      // CNES counts ICU beds inside the existing beds
      note: Number(row.UTI_TOTAL_EXIST) > 0 ? `${sus('UTI_TOTAL_SUS')} · ${t('tile.icuIncluded')}` : sus('UTI_TOTAL_SUS'),
    },
    { label: t('tile.physicians'), value: formatCount(row.total_medicos) },
    { label: t('tile.nurses'), value: formatCount(row.total_enfermeiros) },
    { label: t('tile.admissions'), value: sih ? formatCount(admissions) : '–', note: sih ? t('period.sihShort') : t('tile.notSus') },
    {
      label: t('tile.stay'),
      value: admissions ? t('tile.days', { value: formatNumber(row.media_dias_permanencia, 1) }) : '–',
      note: !sih ? t('tile.notSus') : [stayRank(row, stays), t('period.sihShort')].filter(Boolean).join(' · '),
    },
    deaths ? {
      label: t('tile.deaths'), value: `${formatNumber(deaths.rate, 1)}%`,
      note: t('tile.deathsNote', { expected: formatNumber(deaths.expectedRate, 1) }),
    } : null,
  ].filter(Boolean));
}

/**
 * Deaths in SUS admissions against the deaths the patients' profile predicts. The funnel plot is
 * added by the facility page, which loads the other hospitals (public/data/hospital_mortality.json).
 */
function deathsSection(row, compact) {
  const admissions = Number(row.internacoes_total) || 0;
  if (!admissions) return null;
  const d = deathFigures(row);
  const block = d
    ? el('div', { class: compact ? null : 'deaths-body' },
      keyValues([
        [t('deaths.observed'), t('deaths.observedValue', {
          deaths: formatCount(d.deaths), admissions: formatCount(d.admissions), rate: formatNumber(d.rate, 1),
        })],
        [t('deaths.expected'), t('deaths.expectedValue', {
          rate: formatNumber(d.expectedRate, 1), deaths: formatNumber(d.expected, 0),
        })],
        [t('deaths.ratio'), formatNumber(d.ratio, 2)],
        [t('deaths.band'), d.few ? t('deaths.few') : t(`deaths.band.${d.band}`)],
        ...(d.profile && !d.few && !compact ? profileRows(d.profile) : []),
      ]),
      el('div', { class: 'deaths-plot' }))
    : null;
  const compared = d && !d.few;
  const notes = d ? [t('deaths.method'), compared && electiveCoding(row, d.profile) ? t('deaths.coding') : null,
    compared && d.band === 'below' ? t('deaths.below') : null,
    compared && d.band === 'above' ? t('deaths.above') : null] : [];
  const node = section(t('deaths.title'), block, {
    hint: d ? notes.filter(Boolean).join(' ') : null,
    emptyText: HOSPITAL_TYPES.includes(row.tipo_equipamento) ? t('deaths.noExpected') : t('deaths.notHospital'),
  });
  node.id = 'record-deaths';
  if (d && !compact) node.classList.add('is-wide');
  return node;
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

/** Where the facility's mean stay falls among hospitals with SUS admissions, as the narrative compares it. */
function stayRank(row, stays) {
  const stay = Number(row.media_dias_permanencia);
  if (!stays?.length || !(Number(row.internacoes_total) > 0) || !Number.isFinite(stay)) return null;
  const longer = stays.filter((s) => s < stay).length;
  return t('tile.stayRank', { share: Math.round((100 * longer) / stays.length), count: formatCount(stays.length) });
}

/**
 * @param {object} row  record from infraestrutura_saude
 * @param {{compact?: boolean}} options  compact trims long lists for the side panel
 */
export function renderFacility(row, { compact = false, stays = null } = {}) {
  const limit = compact ? 5 : 0;
  return el('div', { class: `facility${compact ? ' is-compact' : ''}` },
    keyFigures(row, stays),
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
      }),
      deathsSection(row, compact)));
}
