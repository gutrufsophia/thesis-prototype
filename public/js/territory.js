// Surroundings and health tabs of the facility page. Census indicators are computed for the
// radius; health outcomes are only published per district (capital) and per municipality, so
// they live in a tab of their own and every block names the scale it refers to.

import { getDistrictIndicators, getMunicipalIndicators } from './api.js';
import { about, barList, el, keyValues, moreRows, section } from './charts.js';
import { formatCount, formatDistance, formatNumber } from './fields.js';
import { t } from './i18n.js';

// Years with a full calendar year of notifications in the TabNet exports
const SINAN_YEARS = ['2022', '2023', '2024', '2025'];
const SAO_PAULO_CITY = '355030';
// ICD-10 chapters shown individually; the remaining defined chapters are grouped as "other"
const DEATH_CAUSES = ['ix', 'ii', 'x', 'xx', 'xi', 'i'];
// Chapter XVIII (ill-defined causes) ranges from 0.8% to 26.3% of deaths across RMSP
// municipalities, so cause shares are taken over defined deaths and XVIII is shown apart.
const ILL_DEFINED = 'xviii';
const ILL_DEFINED_FLAG_PCT = 10;

let indicatorsPromise = null;
let districtsPromise = null;
let modelsPromise = null;

/** All municipalities keyed by code, plus the metropolitan totals under `region`. */
function loadIndicators() {
  indicatorsPromise ??= getMunicipalIndicators().then((rows) => {
    return { byCode: new Map(rows.map((row) => [row.cd_municipio6, row])), region: sumRows(rows) };
  });
  return indicatorsPromise;
}

const sumRows = (rows) => {
  const total = {};
  for (const row of rows) {
    for (const [key, value] of Object.entries(row)) {
      if (typeof value === 'number') total[key] = (total[key] || 0) + value;
    }
  }
  return total;
};

/**
 * São Paulo city districts keyed by IBGE code. The city reference is the sum of the districts,
 * so both come from the same SMS-SP systems and leave out records without a district.
 */
function loadDistricts() {
  districtsPromise ??= getDistrictIndicators().then((rows) => ({
    byCode: new Map(rows.map((row) => [row.cd_dist, row])),
    city: sumRows(rows),
  }));
  return districtsPromise;
}

/**
 * District expected counts and the share of variation each district model explains: the same
 * static file as the relations page (public/data/relations.json, analysis/outcome_relations.py).
 */
function loadModels() {
  modelsPromise ??= fetch('data/relations.json')
    .then((response) => {
      if (!response.ok) throw new Error(`relations.json: ${response.status}`);
      return response.json();
    })
    .then((data) => ({
      expected: new Map(data.expected.filter((e) => e.scale === 'district').map((e) => [`${e.code}:${e.outcome}`, e])),
      explained: Object.fromEntries(data.models.filter((m) => m.scale === 'district').map((m) => [m.outcome, m.deviance_explained])),
    }));
  return modelsPromise;
}

const per100k = (cases, population) => (population ? (cases / population) * 100000 : null);
const percent = (part, whole) => (whole ? (part / whole) * 100 : null);
const sumYears = (row, prefix) => SINAN_YEARS.reduce((sum, year) => sum + row[`${prefix}_${year}`], 0);

function scopeChip(text, kind) {
  return el('p', { class: `scope scope-${kind}` }, text);
}

function referenceLegend(key = 'ter.referenceLegend') {
  return el('p', { class: 'hint reference-legend' }, el('span', { class: 'reference-key' }), t(key));
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
    scopes.map((scope) => ({ label: scope.label, value: value(scope.data), muted: scope.muted })), options), { note: hint });
}

/** Municipality against the metropolitan region for one municipal indicator. */
function municipalChart(title, home, region, value, options, hint) {
  return section(title, barList([
    { label: home.nome, value: value(home) },
    { label: t('sur.region'), value: value(region), muted: true },
  ], options), { note: hint });
}

/** District against the whole city, both from the SMS-SP systems. */
function districtChart(title, district, city, value, options, hint) {
  return section(title, barList([
    { label: district.nm_dist, value: value(district) },
    { label: t('ter.cityWithDistricts'), value: value(city), muted: true },
  ], options), { note: hint });
}

/** Observed count against the district model's expected count and 95% prediction interval. */
function modelBlock(models, district, outcome) {
  const row = models?.expected.get(`${district.row.cd_dist}:${outcome}`);
  if (!row) return null;
  const where = row.observed > row.upper ? 'above' : row.observed < row.lower ? 'below' : 'within';
  const max = Math.max(row.upper, row.observed) * 1.1 || 1;
  const at = (value) => (value / max).toFixed(4);
  const values = {
    observed: formatCount(row.observed), expected: formatCount(Math.round(row.expected)),
    lower: formatCount(Math.round(row.lower)), upper: formatCount(Math.round(row.upper)),
  };
  return el('section', { class: 'block model-block' },
    el('h3', { text: t('model.title') }),
    el('div', { class: 'model-track', role: 'img', 'aria-label': t('model.aria', { ...values, where: t(`model.${where}`) }) },
      el('span', { class: 'model-band', style: { '--lo': at(row.lower), '--hi': at(row.upper) } }),
      el('span', { class: 'model-expected', style: { '--x': at(row.expected) } }),
      el('span', { class: `model-observed is-${where}`, style: { '--x': at(row.observed) } })),
    el('p', { class: 'model-value' },
      el('strong', { text: t(`model.observed.${outcome}`, values) }), ` · ${t('model.expected', values)} · `,
      el('strong', { text: t(`model.${where}`) })),
    el('p', { class: 'hint model-legend' },
      el('span', { class: 'model-key-dot' }), t('model.legendObserved'),
      el('span', { class: 'model-key-tick' }), t('model.legendExpected'),
      el('span', { class: 'model-key-band' }), t('model.legendBand')),
    about(el('p', {}, t('model.hint', { share: formatNumber(100 * (models.explained[outcome] || 0), 0) }), ' ',
      el('a', { href: 'relations.html#surpresas', text: t('model.link') }))));
}

/** The district's place among the city's districts for one rate, as the narrative ranks it. */
function districtRank(district, rate) {
  const rates = district.all.map(rate).filter((v) => v !== null).sort((a, b) => a - b);
  const own = rate(district.row);
  const fromLow = rates.filter((v) => v < own).length + 1;
  const fromHigh = rates.filter((v) => v > own).length + 1;
  return fromLow <= fromHigh
    ? t('ter.rank.low', { rank: fromLow, count: rates.length })
    : t('ter.rank.high', { rank: fromHigh, count: rates.length });
}

function districtScope(district) {
  return scopeChip(t('ter.scope.district', { name: district.row.nm_dist }), 'district');
}

function municipalScope(home) {
  return scopeChip(t('ter.scope.municipality', { name: home.nome }), 'municipality');
}

const cardTitle = (key) => el('h3', { class: 'card-title', text: t(key) });

// ---------- Surroundings tab: census of the radius, against municipality and region ----------

function summaryCard(surroundings) {
  const radius = surroundings.census.radius;
  const area = surroundings.area_km2;
  // share of the touched tracts' population that lives inside the circle: the basis of rule C03b
  let inside = 0;
  let total = 0;
  for (const feature of surroundings.tracts?.features || []) {
    const p = feature.properties;
    inside += (p.population || 0) * (p.share_inside || 0);
    total += p.population || 0;
  }
  return [
    cardTitle('sur.summary'),
    // Income and residents per household are in the housing card
    keyValues([
      [t('sur.residents'), formatCount(radius.population)],
      [t('sur.households'), formatCount(radius.households)],
      [t('sur.density'), area ? formatCount(Math.round((radius.population || 0) / area)) : '–'],
    ], { numeric: true }),
    moreRows([
      [t('sur.area'), formatNumber(area, 2)],
      [t('sur.tractsLabel'), formatCount(radius.tracts)],
      [t('sur.coverage'), total ? `${formatNumber((100 * inside) / total, 0)}%` : '–'],
    ]),
    about(t('sur.summaryHint')),
  ];
}

function housingCard(surroundings) {
  return [
    cardTitle('sur.housing'),
    contextChart(t('ind.income'), surroundings, (d) => d.income, { prefix: 'R$ ' }, t('sur.incomeHint')),
    contextChart(t('ind.crowding'), surroundings, (d) => d.residents_per_household, { digits: 2 }),
    contextChart(t('ter.resp.crowded', { threshold: formatNumber(surroundings.crowding_threshold, 1) }),
      surroundings, (d) => d.crowded_pct, { digits: 1, suffix: '%' }),
  ];
}

function sanitationCard(surroundings) {
  const lacking = (value) => (value === null ? null : Math.round((100 - value) * 10) / 10);
  return [
    cardTitle('sur.sanitation'),
    contextChart(t('ind.noSewage'), surroundings, (d) => lacking(d.sewage_pct), { digits: 1, suffix: '%' }),
    contextChart(t('ind.precarious'), surroundings, (d) => d.precarious_pct, { digits: 1, suffix: '%' },
      t('ter.precariousHint')),
    contextChart(t('ind.noGarbage'), surroundings, (d) => lacking(d.garbage_pct), { digits: 1, suffix: '%' }),
  ];
}

function accessCard(surroundings) {
  const bands = surroundings.access_bands;
  return [
    cardTitle('ter.access.title'),
    section(t('ter.access.bands'), barList([
      { label: t('ter.access.upto500'), value: bands.upto_500 },
      { label: t('ter.access.upto1000'), value: bands.upto_1000 },
      { label: t('ter.access.upto2000'), value: bands.upto_2000 },
      { label: t('ter.access.over2000'), value: bands.over_2000 },
    ]), { note: t('ter.access.bandsHint', { cnes: t('period.cnes') }) }),
    contextChart(t('ter.access.far'), surroundings, (d) => d.far_primary_pct, { digits: 1, suffix: '%' }),
  ];
}

// ---------- Health tab: outcomes exist only per district (capital) and per municipality ----------

function healthIntro(surroundings, home, district) {
  const others = surroundings.municipalities.filter((m) => m.code !== home.cd_municipio6).map((m) => m.name);
  const parts = [district
    ? t('health.intro.district', { district: district.row.nm_dist })
    : t(home.cd_municipio6 === SAO_PAULO_CITY ? 'health.intro.capital' : 'health.intro.municipality', { name: home.nome })];
  if (others.length) parts.push(t('ter.alsoReaches', { names: others.join(', '), home: home.nome }));
  return parts.join(' ');
}

function tbCard(home, region, district, models) {
  const years = SINAN_YEARS.length;
  const tbRate = (row) => per100k(sumYears(row, 'tuberculose') / years, row.populacao);
  const districtTbRate = (row) => per100k(sumYears(row, 'tb') / years, row.populacao_total);
  return [
    cardTitle('health.tb.title'),
    ...(district ? [
      districtScope(district),
      districtChart(t('ter.resp.tb'), district.row, district.city, districtTbRate, { digits: 1 },
        [t('ter.resp.tbDistrictHint', { count: formatCount(sumYears(district.row, 'tb')) }), districtRank(district, districtTbRate)].join(' ')),
      modelBlock(models, district, 'tb'),
    ] : []),
    municipalScope(home),
    municipalChart(t('ter.resp.tb'), home, region, tbRate, { digits: 1 }, t('ter.resp.tbHint')),
  ];
}

function environmentCard(home, region) {
  const dengue = barList(SINAN_YEARS.map((year) => ({
    label: year,
    value: per100k(home[`dengue_${year}`], home.populacao),
    reference: per100k(region[`dengue_${year}`], region.populacao),
    note: t('ter.cases', { count: formatCount(home[`dengue_${year}`]) }),
  })), { digits: 0 });
  const years = SINAN_YEARS.length;
  return [
    cardTitle('health.env.title'),
    municipalScope(home),
    section(t('ter.env.dengue'), dengue, { note: t('ter.env.dengueHint') }),
    referenceLegend(),
    municipalChart(t('ter.env.lepto'), home, region,
      (row) => per100k(sumYears(row, 'lepto') / years, row.populacao), { digits: 2 },
      t('ter.env.leptoHint', { count: formatCount(sumYears(home, 'lepto')), name: home.nome })),
  ];
}

function maternalCard(home, region, district, models) {
  const teen = (row) => percent(row.nasc_mae_menor_20, row.nasc_idade_conhecida);
  const preterm = (row) => percent(row.nasc_pretermo, row.nasc_gestacao_conhecida);
  const pct = { digits: 1, suffix: '%' };
  return [
    cardTitle('ter.mat.title'),
    ...(district ? [
      districtScope(district),
      districtChart(t('ter.mat.teen'), district.row, district.city, teen, pct),
      modelBlock(models, district, 'teen'),
      districtChart(t('ter.mat.preterm'), district.row, district.city, preterm, pct,
        t('ter.mat.districtHint', { count: formatCount(district.row.nasc_total) })),
    ] : []),
    municipalScope(home),
    municipalChart(t('ter.mat.teen'), home, region, teen, pct),
    municipalChart(t('ter.mat.preterm'), home, region, preterm, pct),
    about(t('ter.mat.hint', { count: formatCount(home.nasc_total) })),
  ];
}

const definedDeaths = (row) => row.obitos_total - row[`obitos_cap_${ILL_DEFINED}`];

function causeShares(row, reference) {
  const share = (r, chapter) => percent(r[`obitos_cap_${chapter}`], definedDeaths(r));
  const listed = (r) => DEATH_CAUSES.reduce((sum, chapter) => sum + r[`obitos_cap_${chapter}`], 0);
  const items = DEATH_CAUSES.map((chapter) => ({
    label: t(`ter.mort.cap.${chapter}`), value: share(row, chapter), reference: share(reference, chapter),
  })).sort((a, b) => b.value - a.value);
  items.push({
    label: t('ter.mort.other'),
    value: percent(definedDeaths(row) - listed(row), definedDeaths(row)),
    reference: percent(definedDeaths(reference) - listed(reference), definedDeaths(reference)),
  });
  return barList(items, { digits: 1, suffix: '%' });
}

function mortalityCard(home, region, district) {
  const illDefined = (row) => percent(row[`obitos_cap_${ILL_DEFINED}`], row.obitos_total);
  const homeIllDefined = illDefined(home);
  return [
    cardTitle('ter.mort.title'),
    ...(district ? [
      districtScope(district),
      section(t('ter.mort.causes'), causeShares(district.row, district.city), {
        note: t('ter.mort.districtHint', { count: formatCount(definedDeaths(district.row)), name: district.row.nm_dist }),
      }),
      referenceLegend('ter.cityReferenceLegend'),
    ] : []),
    municipalScope(home),
    homeIllDefined > ILL_DEFINED_FLAG_PCT
      ? el('p', { class: 'notice', text: t('ter.mort.illDefinedFlag', {
        share: formatNumber(homeIllDefined, 1), name: home.nome }) })
      : null,
    section(t('ter.mort.causes'), causeShares(home, region),
      { note: t('ter.mort.hint', { count: formatCount(definedDeaths(home)), total: formatCount(home.obitos_total) }) }),
    municipalChart(t('ter.mort.illDefined'), home, region, illDefined, { digits: 1, suffix: '%' },
      t('ter.mort.illDefinedHint')),
    referenceLegend(),
  ].filter(Boolean);
}

/** The facility's district, from the first nine digits of its census tract code; null if unavailable. */
async function findDistrict(surroundings) {
  const tract = surroundings.location?.tract;
  if (!tract) return null;
  try {
    const districts = await loadDistricts();
    const row = districts.byCode.get(String(tract).slice(0, 9));
    return row ? { row, city: districts.city, all: [...districts.byCode.values()] } : null;
  } catch (error) {
    console.warn('District indicators unavailable:', error);
    return null;
  }
}

/** Fill the surroundings and health tabs for the current radius. */
export async function renderTerritory(surroundings) {
  const fill = (id, nodes) => document.getElementById(id).replaceChildren(...nodes);
  document.getElementById('surroundings-scope').textContent = t('ter.scope.radius', {
    radius: formatDistance(surroundings.radius_m), census: t('period.census'),
  });
  fill('s-summary', summaryCard(surroundings));
  fill('s-housing', housingCard(surroundings));
  fill('s-sanitation', sanitationCard(surroundings));
  fill('s-access', accessCard(surroundings));

  const healthCards = ['h-tb', 'h-environment', 'h-maternal', 'h-mortality'];
  let indicators;
  try {
    indicators = await loadIndicators();
  } catch (error) {
    for (const id of healthCards) fill(id, [el('p', { class: 'notice is-error', text: t('ter.loadError', { message: error.message }) })]);
    return;
  }
  const home = indicators.byCode.get(surroundings.location?.municipality_code);
  if (!home) return;
  const district = home.cd_municipio6 === SAO_PAULO_CITY ? await findDistrict(surroundings) : null;
  const models = district ? await loadModels().catch((error) => {
    console.warn('District models unavailable:', error);
    return null;
  }) : null;
  document.getElementById('health-intro').textContent = healthIntro(surroundings, home, district);
  fill('h-tb', tbCard(home, indicators.region, district, models).filter(Boolean));
  fill('h-environment', environmentCard(home, indicators.region));
  fill('h-maternal', maternalCard(home, indicators.region, district, models).filter(Boolean));
  fill('h-mortality', mortalityCard(home, indicators.region, district));
}
