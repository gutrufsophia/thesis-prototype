// "Territory and health" cards of the facility page. Each card pairs a local factor,
// computed for the radius, with health outcomes that are only published per
// municipality. Every block is labelled with the scale it refers to.

import { getMunicipalIndicators } from './api.js';
import { barList, el, section } from './charts.js';
import { formatCount, formatDistance, formatNumber } from './fields.js';
import { t } from './i18n.js';

// Years with a full calendar year of notifications in the TabNet exports
const SINAN_YEARS = ['2022', '2023', '2024', '2025'];
const SAO_PAULO_CITY = '355030';
// ICD-10 chapters shown individually; the remaining chapters are grouped as "other"
const DEATH_CAUSES = ['ix', 'ii', 'x', 'xx', 'xi', 'i', 'xviii'];

let indicatorsPromise = null;

/** All municipalities keyed by code, plus the metropolitan totals under `region`. */
function loadIndicators() {
  indicatorsPromise ??= getMunicipalIndicators().then((rows) => {
    const region = {};
    for (const row of rows) {
      for (const [key, value] of Object.entries(row)) {
        if (typeof value === 'number') region[key] = (region[key] || 0) + value;
      }
    }
    return { byCode: new Map(rows.map((row) => [row.cd_municipio6, row])), region };
  });
  return indicatorsPromise;
}

const per100k = (cases, population) => (population ? (cases / population) * 100000 : null);
const percent = (part, whole) => (whole ? (part / whole) * 100 : null);
const sumYears = (row, prefix) => SINAN_YEARS.reduce((sum, year) => sum + row[`${prefix}_${year}`], 0);

function scopeChip(text, kind) {
  return el('p', { class: `scope scope-${kind}` }, text);
}

function referenceLegend() {
  return el('p', { class: 'hint reference-legend' }, el('span', { class: 'reference-key' }), t('ter.referenceLegend'));
}

/** Radius, municipality and region side by side for one census indicator. */
function contextChart(title, surroundings, value, options, hint) {
  const { census, location: place } = surroundings;
  const scopes = [
    { label: t('sur.within', { radius: formatDistance(surroundings.radius_m) }), data: census.radius },
    { label: place?.municipality || t('sur.municipality'), data: census.municipality, muted: true },
    { label: t('sur.region'), data: census.region, muted: true },
  ].filter((scope) => scope.data);
  return section(title, barList(
    scopes.map((scope) => ({ label: scope.label, value: value(scope.data), muted: scope.muted })), options), { hint });
}

/** Municipality against the metropolitan region for one municipal indicator. */
function municipalChart(title, home, region, value, options, hint) {
  return section(title, barList([
    { label: home.nome, value: value(home) },
    { label: t('sur.region'), value: value(region), muted: true },
  ], options), { hint });
}

function municipalScope(surroundings, home) {
  const others = surroundings.municipalities.filter((m) => m.code !== home.cd_municipio6).map((m) => m.name);
  const nodes = [scopeChip(t('ter.scope.municipality', { name: home.nome }), 'municipality')];
  if (others.length) nodes.push(el('p', { class: 'hint', text: t('ter.alsoReaches', { names: others.join(', '), home: home.nome }) }));
  if (home.cd_municipio6 === SAO_PAULO_CITY) nodes.push(el('p', { class: 'hint', text: t('ter.capitalNote') }));
  return nodes;
}

function environmentCard(surroundings, home, region) {
  const lacking = (value) => (value === null ? null : Math.round((100 - value) * 10) / 10);
  const dengue = barList(SINAN_YEARS.map((year) => ({
    label: year,
    value: per100k(home[`dengue_${year}`], home.populacao),
    reference: per100k(region[`dengue_${year}`], region.populacao),
    note: t('ter.cases', { count: formatCount(home[`dengue_${year}`]) }),
  })), { digits: 0 });
  const years = SINAN_YEARS.length;
  return [
    el('h3', { class: 'card-title', text: t('ter.env.title') }),
    scopeChip(t('ter.scope.radius', { radius: formatDistance(surroundings.radius_m), census: t('period.census') }), 'radius'),
    contextChart(t('ind.noSewage'), surroundings, (d) => lacking(d.sewage_pct), { digits: 1, suffix: '%' }),
    contextChart(t('ind.precarious'), surroundings, (d) => d.precarious_pct, { digits: 1, suffix: '%' },
      t('ter.precariousHint')),
    contextChart(t('ind.noGarbage'), surroundings, (d) => lacking(d.garbage_pct), { digits: 1, suffix: '%' }),
    ...municipalScope(surroundings, home),
    section(t('ter.env.dengue'), dengue, { hint: t('ter.env.dengueHint') }),
    referenceLegend(),
    municipalChart(t('ter.env.lepto'), home, region,
      (row) => per100k(sumYears(row, 'lepto') / years, row.populacao), { digits: 2 },
      t('ter.env.leptoHint', { count: formatCount(sumYears(home, 'lepto')), name: home.nome })),
  ];
}

function respiratoryCard(surroundings, home, region) {
  const years = SINAN_YEARS.length;
  return [
    el('h3', { class: 'card-title', text: t('ter.resp.title') }),
    scopeChip(t('ter.scope.radius', { radius: formatDistance(surroundings.radius_m), census: t('period.census') }), 'radius'),
    contextChart(t('ind.crowding'), surroundings, (d) => d.residents_per_household, { digits: 2 }),
    contextChart(t('ter.resp.crowded', { threshold: formatNumber(surroundings.crowding_threshold, 1) }),
      surroundings, (d) => d.crowded_pct, { digits: 1, suffix: '%' }),
    ...municipalScope(surroundings, home),
    municipalChart(t('ter.resp.tb'), home, region,
      (row) => per100k(sumYears(row, 'tuberculose') / years, row.populacao), { digits: 1 }, t('ter.resp.tbHint')),
  ];
}

function accessCard(surroundings) {
  const bands = surroundings.access_bands;
  return [
    el('h3', { class: 'card-title', text: t('ter.access.title') }),
    scopeChip(t('ter.scope.radius', { radius: formatDistance(surroundings.radius_m), census: t('period.census') }), 'radius'),
    section(t('ter.access.bands'), barList([
      { label: t('ter.access.upto500'), value: bands.upto_500 },
      { label: t('ter.access.upto1000'), value: bands.upto_1000 },
      { label: t('ter.access.upto2000'), value: bands.upto_2000 },
      { label: t('ter.access.over2000'), value: bands.over_2000 },
    ]), { hint: t('ter.access.bandsHint', { cnes: t('period.cnes') }) }),
    contextChart(t('ter.access.far'), surroundings, (d) => d.far_primary_pct, { digits: 1, suffix: '%' }),
  ];
}

function maternalCard(surroundings, home, region) {
  return [
    el('h3', { class: 'card-title', text: t('ter.mat.title') }),
    ...municipalScope(surroundings, home),
    municipalChart(t('ter.mat.teen'), home, region,
      (row) => percent(row.nasc_mae_menor_20, row.nasc_idade_conhecida), { digits: 1, suffix: '%' }),
    municipalChart(t('ter.mat.preterm'), home, region,
      (row) => percent(row.nasc_pretermo, row.nasc_gestacao_conhecida), { digits: 1, suffix: '%' }),
    el('p', { class: 'hint', text: t('ter.mat.hint', { count: formatCount(home.nasc_total) }) }),
  ];
}

function mortalityCard(surroundings, home, region) {
  const share = (row, chapter) => percent(row[`obitos_cap_${chapter}`], row.obitos_total);
  const listed = (row) => DEATH_CAUSES.reduce((sum, chapter) => sum + row[`obitos_cap_${chapter}`], 0);
  const items = DEATH_CAUSES.map((chapter) => ({
    label: t(`ter.mort.cap.${chapter}`), value: share(home, chapter), reference: share(region, chapter),
  })).sort((a, b) => b.value - a.value);
  items.push({
    label: t('ter.mort.other'),
    value: percent(home.obitos_total - listed(home), home.obitos_total),
    reference: percent(region.obitos_total - listed(region), region.obitos_total),
  });
  return [
    el('h3', { class: 'card-title', text: t('ter.mort.title') }),
    ...municipalScope(surroundings, home),
    section(t('ter.mort.causes'), barList(items, { digits: 1, suffix: '%' }),
      { hint: t('ter.mort.hint', { count: formatCount(home.obitos_total) }) }),
    referenceLegend(),
  ];
}

/** Fill the territory cards for the current radius. */
export async function renderTerritory(surroundings) {
  const cards = {
    environment: document.getElementById('t-environment'),
    respiratory: document.getElementById('t-respiratory'),
    access: document.getElementById('t-access'),
    maternal: document.getElementById('t-maternal'),
    mortality: document.getElementById('t-mortality'),
  };
  cards.access.replaceChildren(...accessCard(surroundings));

  let indicators;
  try {
    indicators = await loadIndicators();
  } catch (error) {
    for (const key of ['environment', 'respiratory', 'maternal', 'mortality']) {
      cards[key].replaceChildren(el('p', { class: 'notice is-error', text: t('ter.loadError', { message: error.message }) }));
    }
    return;
  }
  const home = indicators.byCode.get(surroundings.location?.municipality_code);
  if (!home) return;
  cards.environment.replaceChildren(...environmentCard(surroundings, home, indicators.region));
  cards.respiratory.replaceChildren(...respiratoryCard(surroundings, home, indicators.region));
  cards.maternal.replaceChildren(...maternalCard(surroundings, home, indicators.region));
  cards.mortality.replaceChildren(...mortalityCard(surroundings, home, indicators.region));
}
